from __future__ import annotations

import json
from pathlib import Path

from app.llm_client import LLMClient
from app.utils.analysis_meta import build_analysis_meta, render_analysis_meta_block
from app.utils.file_utils import write_utf8
from app.utils.json_utils import load_json, write_json


def _to_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _load_prompt_text(filename: str, default_text: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    if prompt_path.exists():
        text = prompt_path.read_text(encoding="utf-8").strip()
        return text or default_text
    return default_text


def _clean_json_text(response_text: str) -> str:
    text = response_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip()
            if candidate.startswith("[") or candidate.startswith("{"):
                return candidate
    return text


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _format_evidence_label(year: str, title: str) -> str:
    if year == "미상":
        return f"과제명: {title}"
    return f"{year}년 과제: {title}"


def _build_default_cards(
    topics: list[str],
    repeated_work: list[str],
    data_assets: list[str],
    automation_candidates: list[str],
    evidence: list[str],
) -> list[dict[str, object]]:
    linked_topics = topics[:4] if topics else ["교육내용 진단", "업무자료 매칭"]
    evidence_lines = evidence[:3] if evidence else ["업무자료에서 반복 업무 패턴이 확인됨"]
    assets = data_assets[:4] if data_assets else ["연구보고서", "발표자료"]

    diagnosis_evidence: list[str] = []
    diagnosis_evidence.extend([f"반복 업무 패턴: {item}" for item in repeated_work[:3]])
    diagnosis_evidence.extend([f"데이터 자산: {item}" for item in data_assets[:3]])
    diagnosis_evidence.extend([f"자동화 후보: {item}" for item in automation_candidates[:3]])
    if not diagnosis_evidence:
        diagnosis_evidence = evidence_lines

    return [
        {
            "idea_name": "교육내용-업무자료 연계 AI 활용 아이디어 진단 도구",
            "applied_work": "교육자료와 부서 업무자료를 연결해 실제 적용 가능한 AI 과제를 발굴",
            "current_problem": "AI 교육을 수강한 뒤 교육내용을 실제 부서 업무에 어떻게 적용할지 구체화하기 어렵습니다.",
            "ai_method": "교육 개념, NTIS 과제 요약, 반복 업무 패턴을 함께 비교해 아이디어 후보를 생성",
            "input_data": assets,
            "expected_output": ["우선 적용 가능한 AI 아이디어 카드", "업무 근거 요약", "도입 우선순위 초안"],
            "expected_effect": "교육내용과 업무자료의 연결 지점을 빠르게 파악해 적용 우선순위를 정할 수 있습니다.",
            "execution_difficulty": "중간",
            "priority": "상",
            "why_fit_dept": "반복 문서 작업과 자료 검토가 많은 부서 업무 특성에 맞습니다.",
            "first_step": "최근 NTIS 과제 10건과 교육 핵심 개념 5개를 먼저 매칭합니다.",
            "evidence_from_work_materials": diagnosis_evidence,
            "linked_education_topics": linked_topics,
            "risk_or_limitation": "입력 자료가 너무 적으면 매칭 결과의 설명력이 떨어질 수 있습니다.",
        },
        {
            "idea_name": "결과표 정리 및 데이터 시각화 자동화",
            "applied_work": "반복적인 결과표 작성과 보고용 시각화",
            "current_problem": "분석결과표 작성과 시각화 작업이 수작업 중심으로 반복됩니다.",
            "ai_method": "입력 데이터의 핵심 열을 읽어 요약표와 기본 그래프를 자동 생성",
            "input_data": assets,
            "expected_output": ["결과표 초안", "기본 시각화 이미지", "보고용 요약문"],
            "expected_effect": "표·그래프 산출 시간을 단축하고 재현 가능한 분석 체계를 구축합니다.",
            "execution_difficulty": "낮음",
            "priority": "상",
            "why_fit_dept": "정기 보고와 결과 정리 업무가 많아 바로 적용하기 쉽습니다.",
            "first_step": "가장 자주 쓰는 결과표 형식을 템플릿으로 고정합니다.",
            "evidence_from_work_materials": repeated_work[:3] or ["분석결과표 작성", "시각화"],
            "linked_education_topics": topics[:5] or ["데이터 시각화", "workflow automation"],
            "risk_or_limitation": "원본 데이터 스키마가 자주 바뀌면 규칙 유지보수가 필요합니다.",
        },
        {
            "idea_name": "업무 문서검색 기반 지식관리(RAG/VectorDB) 체계",
            "applied_work": "과거 과제와 보고서를 빠르게 검색하는 지식관리",
            "current_problem": "기존 연구자료 검색이 비효율적이라 유사 과제 참고에 시간이 걸립니다.",
            "ai_method": "문서 단락을 색인해 검색·질의응답 형태로 재사용",
            "input_data": assets,
            "expected_output": ["유사 과제 검색 결과", "핵심 근거 문장", "질의응답형 검색 화면"],
            "expected_effect": "필요한 문서·근거를 빠르게 찾고 재사용률을 높일 수 있습니다.",
            "execution_difficulty": "높음",
            "priority": "중",
            "why_fit_dept": "연구자료 검색과 근거 확인 업무가 반복됩니다.",
            "first_step": "보고서와 발표자료를 먼저 색인 대상으로 묶습니다.",
            "evidence_from_work_materials": automation_candidates[:4] or ["문서검색", "RAG", "VectorDB"],
            "linked_education_topics": topics[:6] or ["RAG", "VectorDB", "지식관리"],
            "risk_or_limitation": "민감정보 마스킹·접근권한 관리 정책이 선행되어야 합니다.",
        },
    ]


def generate_idea_cards(
    education_concepts_path: Path,
    department_map_path: Path,
    output_dir: Path,
    llm_client: LLMClient | None = None,
) -> dict[str, Path]:
    education_data = load_json(education_concepts_path) if education_concepts_path.exists() else {}
    department_data = load_json(department_map_path) if department_map_path.exists() else {}

    topics = _to_string_list(education_data.get("core_topics", [])) if isinstance(education_data, dict) else []
    education_stats = education_data.get("analysis_stats", {}) if isinstance(education_data, dict) else {}
    repeated_work = _to_string_list(department_data.get("repeated_work_patterns", [])) if isinstance(department_data, dict) else []
    data_assets = _to_string_list(department_data.get("data_assets", [])) if isinstance(department_data, dict) else []
    automation_candidates = _to_string_list(department_data.get("automation_candidates", [])) if isinstance(department_data, dict) else []
    work_areas = _to_string_list(department_data.get("work_area", [])) if isinstance(department_data, dict) else []
    evidence_keywords = _to_string_list(department_data.get("evidence_keywords", [])) if isinstance(department_data, dict) else []
    ai_opportunity_types = _to_string_list(department_data.get("ai_opportunity_types", [])) if isinstance(department_data, dict) else []
    suggested_use_cases = _to_string_list(department_data.get("suggested_ai_use_cases", [])) if isinstance(department_data, dict) else []
    project_count = int(department_data.get("project_count", 0) or 0) if isinstance(department_data, dict) else 0

    evidence: list[str] = []
    if isinstance(department_data, dict):
        timeline = department_data.get("timeline", [])
        if isinstance(timeline, list):
            for item in timeline:
                if not isinstance(item, dict):
                    continue
                year = str(item.get("year", "미상"))
                projects = ", ".join(_to_string_list(item.get("project_titles", [])))
                if projects:
                    evidence.append(_format_evidence_label(year, projects))

    llm_used = False
    fallback_reason = "LLM 미사용"
    cards: list[dict[str, object]] = []

    if llm_client is not None and llm_client.can_use_idea_cards():
        system_prompt = _load_prompt_text(
            "idea_cards_system.txt",
            "교육내용과 업무자료를 연결해 아이디어 카드를 생성하는 시스템 프롬프트입니다.",
        )
        payload = {
            "education_topics": topics,
            "repeated_work": repeated_work,
            "data_assets": data_assets,
            "automation_candidates": automation_candidates,
            "work_areas": work_areas,
            "evidence_keywords": evidence_keywords,
            "ai_opportunity_types": ai_opportunity_types,
            "suggested_use_cases": suggested_use_cases,
            "project_count": project_count,
            "requirements": [
                "반복적인 문서 작성",
                "대량 자료 요약",
                "연구과제/보고서 분류",
                "최신 동향 조사",
                "검사/분석 결과 정리",
                "데이터 품질 점검",
                "업무 일정/진행상황 관리",
                "교육성과 보고 자동화",
                "항생제내성 또는 감염병 관련 정보 구조화",
            ],
            "required_fields": [
                "아이디어명",
                "적용 업무",
                "현재 업무 문제",
                "AI 적용 방식",
                "필요한 입력자료",
                "예상 산출물",
                "기대효과",
                "실행 난이도",
                "우선순위",
                "왜 이 부서에 적합한지",
                "첫 실행 단계",
            ],
        }
        user_prompt = (
            "아래 자료를 근거로 AI 아이디어 카드 3개를 JSON 배열로 작성하세요. "
            "반드시 각 카드에 required_fields를 모두 포함하고, 부서 업무와 연결 이유를 명확히 써야 합니다.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        response = llm_client.chat(system_prompt, user_prompt).strip()
        parsed_cards: list[dict[str, object]] = []
        if response:
            try:
                data = json.loads(_clean_json_text(response))
                if isinstance(data, list):
                    parsed_cards = [item for item in data if isinstance(item, dict)]
                elif isinstance(data, dict):
                    maybe_cards = data.get("cards", [])
                    if isinstance(maybe_cards, list):
                        parsed_cards = [item for item in maybe_cards if isinstance(item, dict)]
            except Exception:
                parsed_cards = []

        if parsed_cards:
            cards = parsed_cards
            llm_used = True
            fallback_reason = ""

    if not cards:
        cards = _build_default_cards(topics, repeated_work, data_assets, automation_candidates, evidence_keywords or evidence)

    analysis_meta = build_analysis_meta(
        llm_used=llm_used,
        generation_mode="LLM" if llm_used else "rule-based fallback",
        fallback_reason=fallback_reason,
        input_file_count=int(education_stats.get("input_file_count", 0) or 0),
        successful_file_count=int(education_stats.get("successful_file_count", 0) or 0),
        failed_file_count=0,
        extracted_char_count=int(education_stats.get("total_extracted_chars", 0) or 0),
        ntis_project_count=project_count,
    )

    json_path = write_json(
        output_dir / "idea_cards.json",
        {
            "generated_with_llm": llm_used,
            "fallback_reason": fallback_reason,
            "analysis_meta": analysis_meta,
            "cards": cards,
        },
    )

    lines: list[str] = ["# AI 활용 아이디어 카드", "", render_analysis_meta_block(analysis_meta).strip(), ""]
    if not llm_used:
        lines.extend(["- LLM 미사용으로 인해 아이디어 품질이 제한될 수 있음", ""])

    for idx, card in enumerate(cards, start=1):
        title = str(card.get("idea_name") or card.get("idea_title") or f"아이디어 {idx}")
        lines.append(f"## {idx}. {title}")
        lines.append(f"- 적용 업무: {card.get('applied_work', card.get('problem', '정보 없음'))}")
        lines.append(f"- 현재 업무 문제: {card.get('current_problem', card.get('problem', '정보 없음'))}")
        lines.append(f"- AI 적용 방식: {card.get('ai_method', '정보 없음')}")
        input_data = card.get("input_data", card.get("applicable_data_or_documents", []))
        if isinstance(input_data, list):
            lines.append("- 필요한 입력자료: " + ", ".join(str(x) for x in input_data))
        else:
            lines.append(f"- 필요한 입력자료: {input_data}")
        expected_output = card.get("expected_output", card.get("applicable_data_or_documents", []))
        if isinstance(expected_output, list):
            lines.append("- 예상 산출물: " + ", ".join(str(x) for x in expected_output))
        else:
            lines.append(f"- 예상 산출물: {expected_output}")
        lines.append(f"- 기대효과: {card.get('expected_effect', '정보 없음')}")
        lines.append(f"- 실행 난이도: {card.get('execution_difficulty', card.get('implementation_difficulty', '정보 없음'))}")
        lines.append(f"- 우선순위: {card.get('priority', '정보 없음')}")
        lines.append(f"- 왜 이 부서에 적합한지: {card.get('why_fit_dept', '정보 없음')}")
        lines.append(f"- 첫 실행 단계: {card.get('first_step', '정보 없음')}")
        evidence_items = card.get("evidence_from_work_materials", [])
        if isinstance(evidence_items, list) and evidence_items:
            lines.append("- 업무자료 근거: " + ", ".join(str(x) for x in evidence_items))
        linked_topics = card.get("linked_education_topics", [])
        if isinstance(linked_topics, list) and linked_topics:
            lines.append("- 연결된 교육내용: " + ", ".join(str(x) for x in linked_topics))
        lines.append(f"- 한계 및 유의사항: {card.get('risk_or_limitation', '정보 없음')}")
        lines.append("")

    md_path = write_utf8(output_dir / "idea_cards.md", "\n".join(lines).strip() + "\n")
    return {"idea_cards_json": json_path, "idea_cards_md": md_path}
