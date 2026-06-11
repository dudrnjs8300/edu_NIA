from __future__ import annotations

import re
from pathlib import Path

from app.llm_client import LLMClient
from app.modules.document_converter import load_converted_documents
from app.utils.file_utils import list_text_inputs, read_utf8, write_utf8
from app.utils.analysis_meta import build_analysis_meta, render_analysis_meta_block
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


def _load_doc_manifest_records(manifest_path: Path) -> dict[str, dict[str, str]]:
    if not manifest_path.exists():
        return {}
    try:
        import json

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = data.get("converted_files", []) if isinstance(data, dict) else []
    mapping: dict[str, dict[str, str]] = {}
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            source_path = str(record.get("source_path", ""))
            if source_path:
                mapping[source_path] = {str(k): str(v) for k, v in record.items()}
        failed_records = data.get("failed_files", []) if isinstance(data, dict) else []
        if isinstance(failed_records, list):
            for record in failed_records:
                if not isinstance(record, dict):
                    continue
                source_path = str(record.get("source_path", ""))
                if source_path and source_path not in mapping:
                    mapping[source_path] = {str(k): str(v) for k, v in record.items()}
    return mapping


def _extraction_preview(text: str, limit: int = 500) -> str:
    cleaned = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    return cleaned[:limit]


def _count_lines(text: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return 0
    return len([line for line in cleaned.splitlines() if line.strip()])


def _extraction_warning(method: str, char_count: int, success: bool) -> str:
    if not success:
        return "추출에 실패했습니다. 원본 형식 또는 변환 결과를 확인하세요."
    if char_count == 0:
        return "텍스트가 추출되지 않았습니다. 이미지 기반 자료일 수 있습니다."
    if char_count < 200:
        if method == "ppt extraction":
            return "PPT 슬라이드가 이미지 위주라 추출된 텍스트가 부족합니다."
        if method == "hwpx xml fallback":
            return "HWPX 변환 결과가 짧습니다. 수동 변환 또는 Kordoc MCP 연계가 필요합니다."
        if method == "stt transcript":
            return "STT 결과가 매우 짧습니다. 음질 또는 화자 분리가 부족했을 수 있습니다."
        return "텍스트가 거의 없습니다. 원본 자료를 다시 확인하세요."
    if char_count < 500 and method == "ppt extraction":
        return "PPT 슬라이드에서 추출된 텍스트가 적습니다. 이미지 기반 자료일 수 있습니다."
    return ""


def _build_extraction_report(input_dir: Path, output_dir: Path) -> tuple[Path, Path, dict[str, int]]:
    transcript_dir = output_dir / "transcripts"
    ppt_extract_dir = output_dir / "ppt_extracts"
    doc_extract_dir = output_dir / "doc_extracts"
    manifest_records = _load_doc_manifest_records(doc_extract_dir / "doc_extracts_manifest.json")

    supported_exts = {".txt", ".md", ".pptx", ".ppt", ".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac", ".hwpx", ".hwp"}
    source_files = sorted(
        [path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in supported_exts],
        key=lambda path: path.name,
    )

    records: list[dict[str, object]] = []
    total_chars = 0
    success_count = 0
    failed_count = 0

    for source_path in source_files:
        suffix = source_path.suffix.lower()
        file_type = suffix.lstrip(".").upper()
        processing_method = "failed"
        extracted_text = ""
        output_path = ""
        success = False

        if suffix in {".txt", ".md"}:
            processing_method = "raw text"
            extracted_text = read_utf8(source_path)
            success = bool(extracted_text.strip())
        elif suffix in {".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac"}:
            md_path = transcript_dir / f"{source_path.stem}.transcript.md"
            txt_path = transcript_dir / f"{source_path.stem}.transcript.txt"
            target_path = txt_path if txt_path.exists() else md_path
            if target_path.exists():
                extracted_text = read_utf8(target_path)
                output_path = str(target_path)
                processing_method = "stt transcript"
                success = bool(extracted_text.strip())
        elif suffix in {".pptx", ".ppt"}:
            md_path = ppt_extract_dir / f"{source_path.stem}.ppt.md"
            if md_path.exists():
                extracted_text = read_utf8(md_path)
                output_path = str(md_path)
                processing_method = "ppt extraction"
                success = bool(extracted_text.strip())
        elif suffix in {".hwpx", ".hwp"}:
            record = manifest_records.get(str(source_path.resolve()))
            if record:
                processing_method = record.get("method", "failed") or "failed"
                output_path = record.get("output_path", "") or ""
                status = (record.get("status", "") or "").lower()
                if status == "success" and output_path:
                    output_file = Path(output_path)
                    if output_file.exists():
                        extracted_text = read_utf8(output_file)
                        success = bool(extracted_text.strip())
                elif suffix == ".hwpx":
                    output_file = doc_extract_dir / f"{source_path.name}.md"
                    if output_file.exists():
                        extracted_text = read_utf8(output_file)
                        output_path = str(output_file)
                        processing_method = record.get("method", "hwpx xml fallback") or "hwpx xml fallback"
                        success = bool(extracted_text.strip())

        char_count = len(extracted_text)
        line_count = _count_lines(extracted_text)
        warning = _extraction_warning(processing_method, char_count, success)
        if success:
            success_count += 1
        else:
            failed_count += 1
        total_chars += char_count

        record = {
            "file_name": source_path.name,
            "file_type": file_type,
            "processing_method": processing_method,
            "output_path": output_path,
            "char_count": char_count,
            "line_count": line_count,
            "success": success,
            "warning": warning,
            "preview": _extraction_preview(extracted_text),
        }
        records.append(record)

    summary_table_lines = ["# 교육자료 추출 리포트", "", "| 파일명 | 유형 | 처리방식 | 글자 수 | 상태 |", "|---|---|---|---:|---|"]
    for record in records:
        status = "성공" if record["success"] else "실패"
        warning = str(record["warning"] or "")
        if warning:
            status = f"{status} / {warning}"
        summary_table_lines.append(
            f"| {record['file_name']} | {record['file_type']} | {record['processing_method']} | {int(record['char_count'])} | {status} |"
        )

    detail_lines = ["", "## 파일별 상세", ""]
    for record in records:
        detail_lines.extend(
            [
                f"### {record['file_name']}",
                f"- 유형: {record['file_type']}",
                f"- 처리방식: {record['processing_method']}",
                f"- 추출 글자 수: {int(record['char_count'])}자",
                f"- 추출 줄 수: {int(record['line_count'])}줄",
                f"- 추출 성공 여부: {'성공' if record['success'] else '실패'}",
                f"- 경고 메시지: {record['warning'] or '없음'}",
                "- 추출 텍스트 미리보기:",
                "```",
                str(record['preview']),
                "```",
                "",
            ]
        )

    md_path = write_utf8(output_dir / "extraction_report.md", "\n".join(summary_table_lines + detail_lines).strip() + "\n")
    json_path = write_json(
        output_dir / "extraction_report.json",
        {
            "summary": {
                "total_files": len(records),
                "success_files": success_count,
                "failed_files": failed_count,
                "total_char_count": total_chars,
            },
            "files": records,
        },
    )
    stats = {
        "total_files": len(records),
        "success_files": success_count,
        "failed_files": failed_count,
        "total_char_count": total_chars,
    }
    return md_path, json_path, stats


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
    extraction_report_md_path, extraction_report_json_path, extraction_stats = _build_extraction_report(input_dir, output_dir)

    merged_sections: list[str] = ["# 통합 교육자료", "", "## 입력자료 요약", ""]
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

    merged_sections.extend(
        [
            f"- 총 입력 파일 수: {extraction_stats['total_files']}개",
            f"- 성공적으로 추출된 파일 수: {extraction_stats['success_files']}개",
            f"- 텍스트 부족/실패 파일 수: {extraction_stats['failed_files']}개",
            f"- 총 추출 글자 수: {extraction_stats['total_char_count']}자",
            "",
            "## 주의가 필요한 파일",
        ]
    )
    report_data = []
    try:
        import json

        report_data = json.loads(extraction_report_json_path.read_text(encoding="utf-8")).get("files", [])
    except Exception:
        report_data = []
    if isinstance(report_data, list):
        for record in report_data:
            if not isinstance(record, dict):
                continue
            warning = str(record.get("warning", "")).strip()
            if not warning and int(record.get("char_count", 0) or 0) >= 200:
                continue
            merged_sections.append(
                f"- {record.get('file_name', 'unknown')}: {warning or '추출 텍스트 부족 또는 실패'}"
            )
    if merged_sections[-1] == "## 주의가 필요한 파일":
        merged_sections.append("- 없음")
    merged_sections.extend(["", "## 병합 원문"])

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

    meta_block = render_analysis_meta_block(
        build_analysis_meta(
            llm_used=llm_used == "사용함",
            generation_mode="LLM" if llm_used == "사용함" else "rule-based fallback",
            fallback_reason="LLM 미사용" if llm_used != "사용함" else "",
            input_file_count=extraction_stats["total_files"],
            successful_file_count=extraction_stats["success_files"],
            failed_file_count=extraction_stats["failed_files"],
            extracted_char_count=extraction_stats["total_char_count"],
        )
    )
    summary_text = meta_block + "\n" + summary_text

    summary_path = write_utf8(output_dir / "education_summary.md", summary_text)

    concepts = {
        "education_title": "AI 교육자료 분석",
        "source_files": source_files,
        "core_topics": core_topics,
        "practical_methods": _build_practical_methods(core_topics),
        "llm_used": llm_used == "사용함",
        "analysis_stats": {
            "input_file_count": extraction_stats["total_files"],
            "successful_file_count": extraction_stats["success_files"],
            "failed_file_count": extraction_stats["failed_files"],
            "total_extracted_chars": extraction_stats["total_char_count"],
        },
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
        "extraction_report_md": extraction_report_md_path,
        "extraction_report_json": extraction_report_json_path,
    }
