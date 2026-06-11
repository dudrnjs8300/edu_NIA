from __future__ import annotations

import re
from pathlib import Path

from app.llm_client import LLMClient
from app.modules.document_converter import load_converted_documents
from app.utils.file_utils import list_text_inputs, read_utf8, write_utf8
from app.utils.json_utils import write_json
from app.modules.ppt_processor import extract_ppt_files


KEYWORDS: list[str] = [
    "RAG",
    "VectorDB",
    "AI Agent",
    "workflow automation",
    "STT",
    "OCR",
    "문서분석",
    "데이터 시각화",
    "자동화",
    "보고서",
    "요약",
    "지식관리",
]


def _detect_topics(text: str) -> list[str]:
    lowered = text.lower()
    detected: list[str] = []
    for keyword in KEYWORDS:
        if keyword.lower() in lowered:
            detected.append(keyword)
    return detected


def _build_practical_methods(core_topics: list[str]) -> list[dict[str, str]]:
    methods: list[dict[str, str]] = []
    topic_set = set(core_topics)

    if {"요약", "보고서"} & topic_set:
        methods.append(
            {
                "method": "보고서 요약 자동화",
                "description": "보고서 본문에서 핵심 문장과 섹션을 추출해 요약 초안을 생성",
                "possible_use": "주간/월간 보고서 초안 작성 시간 단축",
            }
        )

    if {"문서분석", "지식관리", "RAG", "VectorDB"} & topic_set:
        methods.append(
            {
                "method": "문서 검색 기반 지식 활용",
                "description": "업무 문서를 색인하고 주제별로 검색 가능한 형태로 구조화",
                "possible_use": "기존 연구자료 재활용, 유사 과제 참고 속도 향상",
            }
        )

    if {"데이터 시각화", "자동화", "workflow automation"} & topic_set:
        methods.append(
            {
                "method": "반복 분석·시각화 워크플로우 표준화",
                "description": "정기 분석 절차를 단계별 템플릿으로 고정해 반복 수행",
                "possible_use": "결과표 작성 및 시각화 산출물의 일관성 확보",
            }
        )

    if not methods:
        methods.append(
            {
                "method": "업무 단계 구조화",
                "description": "교육자료와 업무자료를 연결해 자동화 후보 단계를 정의",
                "possible_use": "AI 적용 우선순위 도출",
            }
        )

    return methods


def _list_transcript_inputs(transcript_dir: Path) -> list[Path]:
    if not transcript_dir.exists():
        return []
    return sorted(
        [path for path in transcript_dir.glob("*.transcript.md") if path.is_file()],
        key=lambda path: path.name,
    )


def _list_ppt_extract_inputs(ppt_extract_dir: Path) -> list[Path]:
    if not ppt_extract_dir.exists():
        return []
    return sorted(
        [path for path in ppt_extract_dir.glob("*.ppt.md") if path.is_file()],
        key=lambda path: path.name,
    )


def _extract_source_file_name(transcript_text: str) -> str:
    match = re.search(r"^- 원본 파일:\s*(.+)$", transcript_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def _extract_ppt_source_file_name(ppt_text: str) -> str:
    return _extract_source_file_name(ppt_text)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _load_prompt_text(filename: str, default_text: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    if prompt_path.exists():
        return read_utf8(prompt_path).strip() or default_text
    return default_text


def _extract_key_lines(text: str, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("##"):
            continue
        if line in {"본문", "텍스트 없음", "발표자 노트"}:
            continue
        if len(line) < 6:
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return _dedupe_preserve_order(lines)


def _build_rule_based_education_summary(
    core_topics: list[str],
    combined_text: str,
    source_files: list[str],
) -> str:
    key_lines = _extract_key_lines(combined_text, limit=5)
    application_lines = [
        "연구보고서 요약 자동화",
        "부서 데이터 정리 및 결과표 자동 생성",
        "업무 문서 검색 및 지식관리 체계화",
    ]
    implication_lines = [
        f"입력 자료 {len(source_files)}개를 함께 보면 교육 내용과 업무자료의 연결 지점을 더 명확히 파악할 수 있습니다.",
        "STT transcript와 PPT 추출본을 포함하면 교육 맥락을 더 풍부하게 반영할 수 있습니다.",
        "반복 업무와 문서 검색 업무를 중심으로 즉시 적용 가능한 AI 활용 과제를 찾는 데 도움이 됩니다.",
    ]

    lines = [
        "# 교육자료 요약",
        "",
        "## 핵심 주제",
    ]
    if core_topics:
        lines.extend([f"- {topic}" for topic in core_topics[:10]])
    else:
        lines.append("- 탐지된 핵심 주제 없음")

    lines.extend([
        "",
        "## 주요 내용",
    ])
    if key_lines:
        lines.extend([f"- {line}" for line in key_lines])
    else:
        lines.append("- 교육자료에서 요약할 주요 내용이 충분하지 않습니다.")

    lines.extend([
        "",
        "## 업무 적용 가능성",
    ])
    lines.extend([f"- {item}" for item in application_lines])

    lines.extend([
        "",
        "## 교육에서 얻은 시사점",
    ])
    lines.extend([f"- {item}" for item in implication_lines])

    lines.extend([
        "",
        "## LLM 사용 여부",
        "- 사용하지 않음",
    ])
    return "\n".join(lines).strip() + "\n"


def _build_llm_summary(
    llm_client: LLMClient | None,
    combined_text: str,
    core_topics: list[str],
    source_files: list[str],
) -> str:
    if llm_client is None or not llm_client.can_use_education_summary():
        return ""

    system_prompt = _load_prompt_text(
        "education_summary_system.txt",
        "교육자료 요약을 한국어 Markdown으로 작성하는 시스템 프롬프트입니다. 반드시 지정된 섹션 구조를 유지하세요.",
    )
    max_input_chars = getattr(llm_client.settings, "max_input_chars", 6000)
    compressed_text = combined_text[: max_input_chars]
    key_lines = _extract_key_lines(combined_text, limit=8)
    user_prompt = "\n".join(
        [
            "다음 자료를 바탕으로 아래 형식의 한국어 Markdown 요약을 작성하세요.",
            "반드시 다음 섹션을 유지하세요:",
            "# 교육자료 요약",
            "## 핵심 주제",
            "## 주요 내용",
            "## 업무 적용 가능성",
            "## 교육에서 얻은 시사점",
            "## LLM 사용 여부",
            "",
            f"핵심 주제 후보: {', '.join(core_topics) if core_topics else '없음'}",
            f"원본 파일: {', '.join(source_files) if source_files else '없음'}",
            f"핵심 추출 문장: {' | '.join(key_lines) if key_lines else '없음'}",
            "",
            "교육자료 내용:",
            compressed_text,
        ]
    )
    response = llm_client.chat(system_prompt, user_prompt).strip()
    if not response:
        return ""
    required_sections = [
        "# 교육자료 요약",
        "## 핵심 주제",
        "## 주요 내용",
        "## 업무 적용 가능성",
        "## 교육에서 얻은 시사점",
        "## LLM 사용 여부",
    ]
    if all(section in response for section in required_sections):
        return response if response.endswith("\n") else response + "\n"
    return ""


def process_education(input_dir: Path, output_dir: Path, llm_client: LLMClient | None = None) -> dict[str, Path]:
    files = list_text_inputs(input_dir)
    doc_extract_dir = output_dir / "doc_extracts"
    files.extend(load_converted_documents(input_dir, doc_extract_dir))
    transcript_dir = output_dir / "transcripts"
    transcript_files = _list_transcript_inputs(transcript_dir)
    try:
        extract_ppt_files(input_dir=input_dir, output_dir=output_dir, force=False)
    except RuntimeError as exc:
        print(str(exc))
    ppt_extract_dir = output_dir / "ppt_extracts"
    ppt_extract_files = _list_ppt_extract_inputs(ppt_extract_dir)

    merged_sections: list[str] = ["# 교육자료 통합본", ""]
    source_files: list[str] = []
    merged_raw_parts: list[str] = []

    for file_path in files:
        source_files.append(file_path.name)
        content = read_utf8(file_path).strip()
        merged_sections.append(f"## 파일: {file_path.name}")
        merged_sections.append("")
        merged_sections.append(content)
        merged_sections.append("")
        merged_raw_parts.append(content)

    for transcript_path in transcript_files:
        content = read_utf8(transcript_path).strip()
        if not content:
            continue
        source_files.append(transcript_path.name)
        source_files.append(transcript_path.with_suffix(".txt").name)
        source_files.append(_extract_source_file_name(content))
        merged_sections.append(f"## 파일: {transcript_path.name}")
        merged_sections.append("")
        merged_sections.append(content)
        merged_sections.append("")
        merged_raw_parts.append(content)

    for ppt_extract_path in ppt_extract_files:
        content = read_utf8(ppt_extract_path).strip()
        if not content:
            continue
        source_files.append(ppt_extract_path.name)
        source_files.append(_extract_ppt_source_file_name(content))
        merged_sections.append(f"## 파일: {ppt_extract_path.name}")
        merged_sections.append("")
        merged_sections.append(content)
        merged_sections.append("")
        merged_raw_parts.append(content)

    source_files = _dedupe_preserve_order(source_files)

    merged_text = "\n".join(merged_sections).strip() + "\n"
    merged_path = write_utf8(output_dir / "education_merged.md", merged_text)

    combined_text = "\n".join(merged_raw_parts)
    core_topics = _detect_topics(combined_text)

    llm_summary = _build_llm_summary(llm_client, combined_text, core_topics, source_files)
    if llm_summary:
        summary_text = llm_summary
        llm_used = "사용함"
    else:
        summary_text = _build_rule_based_education_summary(core_topics, combined_text, source_files)
        llm_used = "사용하지 않음"

    summary_path = write_utf8(output_dir / "education_summary.md", summary_text)

    concepts = {
        "education_title": "AI 교육자료 분석",
        "source_files": source_files,
        "core_topics": core_topics,
        "practical_methods": _build_practical_methods(core_topics),
        "llm_used": llm_used == "사용함",
        "key_messages": [
            "교육자료와 업무자료를 연결하여 실제 적용 가능한 AI 활용 아이디어를 도출하는 것이 중요합니다."
        ],
        "possible_applications": [
            "연구보고서 요약 자동화",
            "부서 데이터 정리 및 결과표 자동 생성",
            "업무 문서 검색 및 지식관리 체계화",
        ],
    }
    concepts_path = write_json(output_dir / "education_concepts.json", concepts)

    return {
        "education_merged": merged_path,
        "education_summary": summary_path,
        "education_concepts": concepts_path,
    }
