from __future__ import annotations

from pathlib import Path

from app.llm_client import LLMClient
from app.utils.analysis_meta import build_analysis_meta, render_analysis_meta_block
from app.utils.file_utils import read_utf8, write_utf8
from app.utils.json_utils import read_json


def _read_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return read_utf8(path)


def _load_json_if_exists(path: Path) -> object:
    if not path.exists():
        return {}
    return read_json(path)


def _load_idea_cards_payload(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    payload = _load_json_if_exists(path)
    if isinstance(payload, dict):
        cards = payload.get("cards", [])
        meta = payload.get("analysis_meta", {})
        if isinstance(cards, list):
            return [card for card in cards if isinstance(card, dict)], meta if isinstance(meta, dict) else {}
    if isinstance(payload, list):
        return [card for card in payload if isinstance(card, dict)], {}
    return [], {}


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _limit(items: list[str], limit: int, default: str = "정보 없음") -> list[str]:
    trimmed = [item for item in items if str(item).strip()]
    return trimmed[:limit] if trimmed else [default]


def _bullets(items: list[str], default: str = "정보 없음", indent: str = "- ") -> list[str]:
    return [f"{indent}{item}" for item in items] if items else [f"{indent}{default}"]


def _table_lines(rows: list[tuple[str, str]]) -> list[str]:
    lines = ["| 항목 | 내용 |", "|---|---|"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return lines


def _load_prompt_text(filename: str, default_text: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    if prompt_path.exists():
        return read_utf8(prompt_path).strip() or default_text
    return default_text


def _report_meta_block(
    *,
    education_summary_text: str,
    concepts: dict[str, object],
    work_map: dict[str, object],
    idea_meta: dict[str, object] | None,
    llm_client: LLMClient | None,
) -> str:
    stats = concepts.get("analysis_stats", {}) if isinstance(concepts, dict) else {}
    generated_with_llm = bool(idea_meta.get("generated_with_llm", False)) if isinstance(idea_meta, dict) else False
    if not generated_with_llm and llm_client is not None:
        generated_with_llm = bool(llm_client.is_enabled())
    last_error = ""
    if llm_client is not None:
        last_error = str(getattr(llm_client, "last_error_message", "") or "")
    if isinstance(idea_meta, dict):
        fallback_reason = str(idea_meta.get("fallback_reason", "") or "").strip()
    else:
        fallback_reason = ""
    meta = build_analysis_meta(
        llm_used=generated_with_llm,
        generation_mode=llm_client.current_mode() if llm_client is not None else "rule-based fallback",
        fallback_reason=fallback_reason or last_error or ("LLM 미사용" if not generated_with_llm else ""),
        input_file_count=int(stats.get("input_file_count", 0) or 0) if isinstance(stats, dict) else 0,
        successful_file_count=int(stats.get("successful_file_count", 0) or 0) if isinstance(stats, dict) else 0,
        failed_file_count=int(stats.get("failed_file_count", 0) or 0) if isinstance(stats, dict) else 0,
        extracted_char_count=int(stats.get("total_extracted_chars", 0) or 0) if isinstance(stats, dict) else 0,
        ntis_project_count=int(work_map.get("project_count", 0) or 0) if isinstance(work_map, dict) else 0,
        last_llm_error=last_error,
    )
    return render_analysis_meta_block(meta)


def _strip_leading_meta_block(text: str) -> str:
    marker = "# 교육자료 요약"
    index = text.find(marker)
    if index > 0:
        return text[index:]
    return text


def _build_education_result_report(
    education_summary_text: str,
    concepts: dict[str, object],
    work_map: dict[str, object],
    idea_cards: list[dict[str, object]],
    meta_block: str = "",
) -> str:
    core_topics = _limit(_string_list(concepts.get("core_topics", [])), 10, "핵심 주제 없음")
    key_messages = _limit(_string_list(concepts.get("key_messages", [])), 3, "주요 메시지 없음")
    repeated_work_patterns = _limit(_string_list(work_map.get("repeated_work_patterns", [])), 12, "반복 업무 없음")
    automation_candidates = _limit(_string_list(work_map.get("automation_candidates", [])), 12, "자동화 후보 없음")

    result_lines = [
        "# 교육결과 보고서",
        "",
        meta_block.strip(),
        "",
        "## 기본 정보",
    ]
    result_lines.extend(
        _table_lines(
            [
                ("진행자", ""),
                ("활동일시", ""),
                ("학습주제", "AI 교육내용 기반 업무 적용 아이디어 발굴"),
                ("학습방법", "교육자료 분석 및 업무자료 연계 실습"),
                ("강의·발제자", ""),
                ("참여자", ""),
            ]
        )
    )
    result_lines.extend(
        [
            "",
            "## 강의·발제내용 요약",
            "- 교육자료에서 확인된 핵심 AI 개념과 주요 메시지를 정리한다.",
            "- education_summary.md와 education_concepts.json을 활용한다.",
            "- 교육에서 다룬 핵심 주제:",
        ]
    )
    result_lines.extend(_bullets(core_topics, "핵심 주제 없음", indent="  - "))
    result_lines.extend(
        [
            "- 핵심 메시지:",
        ]
    )
    result_lines.extend(_bullets(key_messages, "주요 메시지 없음", indent="  - "))
    result_lines.extend(
        [
            "",
            "## 토론 주요내용 요약",
            "- AI 교육내용을 실제 업무에 어떻게 연결할 수 있는지 정리한다.",
            "- idea_cards.md와 department_work_map.json을 활용한다.",
            "- NTIS 과제목록 또는 부서 업무자료에서 확인된 반복 업무:",
        ]
    )
    result_lines.extend(_bullets(repeated_work_patterns, "반복 업무 없음", indent="  - "))
    result_lines.extend(
        [
            "- 자동화 가능 업무:",
        ]
    )
    result_lines.extend(_bullets(automation_candidates, "자동화 가능 업무 없음", indent="  - "))
    result_lines.extend(
        [
            "- RAG/VectorDB 기반 지식관리 가능성:",
            "  - 교육내용과 업무자료 연결을 통해 업무 적용 시나리오를 구체화할 수 있다.",
            "",
            "## 토론결과(개선대책)",
            "- 교육자료와 업무자료를 함께 분석하여 AI 적용 가능 지점을 진단한다.",
            "- 단순한 교육내용 요약이 아니라 실행 가능한 AI 활용 아이디어 카드로 전환한다.",
            "- 우선 NTIS CSV와 Markdown 자료를 대상으로 MVP를 구현한다.",
            "- 향후 STT, OCR, HWPX 변환, VectorDB, Ollama 연계를 단계적으로 확장한다.",
            "",
            "## 실행계획",
            "- NTIS CSV 기반 부서 업무지도 생성",
            "- 교육자료 기반 핵심 AI 개념 추출",
            "- 교육내용-업무자료 매칭",
            "- AI 활용 아이디어 카드 생성",
            "- 교육결과 보고서 초안 자동 생성",
            "- 향후 Ollama 기반 요약·진단 기능 연계",
            "",
            "## 기대효과",
            "- AI 교육 후 실제 업무 적용 방향을 빠르게 도출할 수 있다.",
            "- 부서의 반복 업무와 데이터 자산을 구조적으로 파악할 수 있다.",
            "- 연구성과 보고, 자료 정리, 문서검색, 아이디어 도출 업무를 효율화할 수 있다.",
            "- 향후 부서 단위 AI 활용 과제 발굴에 활용할 수 있다.",
            "",
            "## 학습총평",
            "- 이번 교육내용은 RAG, VectorDB, AI Agent, 자동화 워크플로우를 실제 연구행정·연구분석 업무에 연결할 수 있다는 점에서 의미가 있다.",
            "- 교육내용을 부서 업무자료와 함께 분석하면 단순 학습을 넘어 실제 적용 가능한 AI 활용 과제로 발전시킬 수 있다.",
            "",
            "## 특이사항",
            "- 없음",
            "",
        ]
    )

    return "\n".join(result_lines).strip() + "\n"


def _build_ai_diagnosis_report(
    work_map: dict[str, object],
    idea_cards: list[dict[str, object]],
    llm_client: LLMClient | None = None,
    meta_block: str = "",
) -> str:
    project_count = int(work_map.get("project_count", 0) or 0)
    years = _string_list(work_map.get("years", []))
    major_work_areas = _limit(_string_list(work_map.get("major_work_areas", [])), 10, "정보 없음")
    repeated_work_patterns = _limit(_string_list(work_map.get("repeated_work_patterns", [])), 10, "정보 없음")
    data_assets = _limit(_string_list(work_map.get("data_assets", [])), 10, "정보 없음")
    automation_candidates = _limit(_string_list(work_map.get("automation_candidates", [])), 10, "정보 없음")
    idea_titles = [str(card.get("idea_title", "")).strip() for card in idea_cards if isinstance(card, dict) and str(card.get("idea_title", "")).strip()]

    def note_for(label: str, items: list[str]) -> str:
        return "가능" if items and items[0] != "정보 없음" else "검토 필요"

    lines = [
        "# AI 활용 진단 보고서",
        "",
        meta_block.strip(),
        "",
        "## 1. 분석 개요",
        "- NTIS 과제목록과 교육자료를 기반으로 부서 업무와 AI 교육내용의 연결 가능성을 분석했습니다.",
        f"- 분석 과제 수: {project_count}건",
        f"- 분석 연도: {', '.join(years) if years else '정보 없음'}",
        "",
        "## 2. 부서 업무 특성",
        "- 주요 업무영역:",
        *_bullets(major_work_areas, "정보 없음", indent="  - "),
        "- 반복 업무:",
        *_bullets(repeated_work_patterns, "정보 없음", indent="  - "),
        "- 주요 데이터 자산:",
        *_bullets(data_assets, "정보 없음", indent="  - "),
        "",
        "## 3. AI 적용 가능 지점",
        f"- 자동 요약: {note_for('자동 요약', automation_candidates)}",
        f"- 문서검색/RAG: {note_for('문서검색/RAG', automation_candidates)}",
        f"- VectorDB 기반 지식관리: {note_for('VectorDB 기반 지식관리', automation_candidates)}",
        f"- 보고서 초안 생성: {note_for('보고서 초안 생성', automation_candidates)}",
        f"- 데이터 시각화: {note_for('데이터 시각화', automation_candidates)}",
        f"- 과제 유사도 검색: {note_for('과제 유사도 검색', automation_candidates)}",
        f"- 업무 자동화 후보 탐색: {note_for('업무 자동화 후보 탐색', automation_candidates)}",
        "",
        "## 4. 우선 추진 아이디어",
    ]
    if idea_titles:
        for idx, title in enumerate(idea_titles[:3], start=1):
            lines.append(f"- {idx}. {title}")
    else:
        lines.append("- 아이디어 카드가 없습니다.")
    lines.extend(
        [
            "",
            "## 5. MVP 제안",
            "- NTIS CSV 입력",
            "- 교육자료 입력",
            "- 부서 업무지도 생성",
            "- AI 활용 아이디어 카드 생성",
            "- 교육결과 보고서 초안 생성",
            "",
            "## 6. 한계 및 유의사항",
            "- NTIS CSV는 과제 메타데이터 중심이므로 실제 연구결과보고서의 세부 내용과 차이가 있을 수 있습니다.",
            "- 규칙 기반 분석은 키워드 누락 가능성이 있으므로 향후 LLM 기반 요약과 검토 기능을 추가할 수 있습니다.",
            "- 민감자료를 사용할 경우 비식별화와 접근권한 관리가 필요합니다.",
            "",
        ]
    )
    draft = "\n".join(lines).strip() + "\n"

    if llm_client is None or not llm_client.can_use_ai_diagnosis():
        return draft

    system_prompt = _load_prompt_text(
        "ai_diagnosis_system.txt",
        "AI 활용 진단 보고서를 한국어 Markdown으로 다듬는 시스템 프롬프트입니다.",
    )
    user_prompt = "\n".join(
        [
            "아래 보고서를 더 자연스럽고 보고서답게 다듬으세요.",
            "섹션 구조는 반드시 그대로 유지하세요:",
            "# AI 활용 진단 보고서",
            "## 1. 분석 개요",
            "## 2. 부서 업무 특성",
            "## 3. AI 적용 가능 지점",
            "## 4. 우선 추진 아이디어",
            "## 5. MVP 제안",
            "## 6. 한계 및 유의사항",
            "과장하지 말고, 실무 적용 관점의 표현으로 정리하세요.",
            "",
            draft,
        ]
    )
    response = llm_client.chat(system_prompt, user_prompt).strip()
    required_sections = [
        "# AI 활용 진단 보고서",
        "## 1. 분석 개요",
        "## 2. 부서 업무 특성",
        "## 3. AI 적용 가능 지점",
        "## 4. 우선 추진 아이디어",
        "## 5. MVP 제안",
        "## 6. 한계 및 유의사항",
    ]
    if response and all(section in response for section in required_sections):
        return response if response.endswith("\n") else response + "\n"
    return draft


def export_final_packet(
    workspace_root: Path,
    output_dir: Path,
    llm_client: LLMClient | None = None,
) -> dict[str, Path]:
    education_summary_path = workspace_root / "02_education_processed" / "education_summary.md"
    education_concepts_path = workspace_root / "02_education_processed" / "education_concepts.json"
    report_summaries_path = workspace_root / "05_department_analysis" / "report_summaries.jsonl"
    department_map_path = workspace_root / "05_department_analysis" / "department_work_map.json"
    department_timeline_path = workspace_root / "05_department_analysis" / "department_timeline.md"
    idea_cards_json_path = workspace_root / "06_matching_output" / "idea_cards.json"
    idea_cards_md_path = workspace_root / "06_matching_output" / "idea_cards.md"
    education_result_report_path = output_dir / "education_result_report.md"
    ai_diagnosis_report_path = output_dir / "AI_diagnosis_report.md"

    education_summary_text = _read_if_exists(education_summary_path)
    concepts = _load_json_if_exists(education_concepts_path)
    work_map = _load_json_if_exists(department_map_path)
    idea_cards, idea_meta = _load_idea_cards_payload(idea_cards_json_path)
    if not isinstance(concepts, dict):
        concepts = {}
    if not isinstance(work_map, dict):
        work_map = {}

    meta_block = _report_meta_block(
        education_summary_text=education_summary_text,
        concepts=concepts,
        work_map=work_map,
        idea_meta=idea_meta,
        llm_client=llm_client,
    )

    ai_diagnosis_report_text = _build_ai_diagnosis_report(work_map, idea_cards, llm_client=llm_client, meta_block=meta_block)
    ai_diagnosis_report_written = write_utf8(ai_diagnosis_report_path, ai_diagnosis_report_text)

    education_result_report_text = _build_education_result_report(
        education_summary_text=education_summary_text,
        concepts=concepts,
        work_map=work_map,
        idea_cards=idea_cards,
        meta_block=meta_block,
    )
    education_result_report_written = write_utf8(education_result_report_path, education_result_report_text)

    packet_lines = [
        "# 최종 입력 패킷",
        "",
        "## 교육 요약",
        education_summary_text or "자료 없음",
        "",
        "## 교육 개념 JSON",
        _read_if_exists(education_concepts_path) or "자료 없음",
        "",
        "## 보고서 요약 JSONL",
        _read_if_exists(report_summaries_path) or "자료 없음",
        "",
        "## 부서 업무 맵 JSON",
        _read_if_exists(department_map_path) or "자료 없음",
        "",
        "## 부서 타임라인",
        _read_if_exists(department_timeline_path) or "자료 없음",
        "",
        "## 아이디어 카드 JSON",
        _read_if_exists(idea_cards_json_path) or "자료 없음",
        "",
        "## 아이디어 카드 Markdown",
        _read_if_exists(idea_cards_md_path) or "자료 없음",
        "",
        "## AI 활용 진단 보고서",
        _read_if_exists(ai_diagnosis_report_written) or "자료 없음",
        "",
        "## 교육결과 보고서",
        _read_if_exists(education_result_report_written) or "자료 없음",
        "",
    ]
    packet_path = write_utf8(output_dir / "final_input_packet.md", "\n".join(packet_lines).strip() + "\n")

    education_summary_body = _strip_leading_meta_block(education_summary_text)

    final_report_lines = [
        "# 최종 보고서 초안",
        "",
        meta_block.strip(),
        "",
        "## 1. 추진 배경",
        "교육자료와 부서 업무자료를 연결해 실제 적용 가능한 AI 활용 과제를 도출하기 위해 본 분석을 수행했습니다.",
        "",
        "## 2. 교육내용 요약",
        education_summary_body or "교육 요약 자료가 없습니다.",
        "",
        "## 3. 부서 업무자료 분석 결과",
        _read_if_exists(department_timeline_path) or "부서 업무 타임라인 자료가 없습니다.",
        "",
        "## 4. AI 활용 아이디어",
        _read_if_exists(idea_cards_md_path) or "아이디어 카드 자료가 없습니다.",
        "",
        "## 5. 교육결과 보고서 활용 방안",
        "- education_result_report.md를 부서 회의와 검토용 초안으로 활용합니다.",
        "- 교육결과 보고서를 통해 교육내용과 업무자료의 연결 지점을 빠르게 검토합니다.",
        "- 보고서 초안을 바탕으로 AI 활용 아이디어 카드의 우선순위를 정리합니다.",
        "",
        "## 6. 향후 계획",
        "- 아이디어 카드별 우선순위를 정하고 단기 PoC를 수행합니다.",
        "- 데이터 품질 기준과 문서 관리 정책을 정비합니다.",
        "- 단계적으로 자동화 범위를 확대하고 성과 지표를 추적합니다.",
        "",
    ]
    draft_path = write_utf8(output_dir / "final_report_draft.md", "\n".join(final_report_lines).strip() + "\n")
    return {
        "AI_diagnosis_report": ai_diagnosis_report_written,
        "education_result_report": education_result_report_written,
        "final_input_packet": packet_path,
        "final_report_draft": draft_path,
    }
