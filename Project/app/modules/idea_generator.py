from __future__ import annotations

from pathlib import Path

from app.utils.file_utils import write_utf8
from app.utils.json_utils import load_json, write_json


def _to_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return []


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

    card_1 = {
        "idea_title": "교육내용-업무자료 연계 AI 활용 아이디어 진단 도구",
        "problem": "AI 교육을 수강한 뒤 교육내용을 실제 부서 업무에 어떻게 적용할지 구체화하기 어렵습니다.",
        "evidence_from_work_materials": diagnosis_evidence,
        "linked_education_topics": linked_topics,
        "applicable_data_or_documents": assets,
        "expected_effect": "교육내용과 업무자료의 연결 지점을 빠르게 파악해 적용 우선순위를 정할 수 있습니다.",
        "implementation_difficulty": "중간",
        "mvp_scope": "교육자료 요약, 업무자료 요약, 교육내용-업무자료 매칭, AI 활용 아이디어 카드 생성",
        "future_expansion": "부서별 추천 점수화, 유사 과제 비교, 적용 로드맵 생성 기능 추가",
        "risk_or_limitation": "입력 자료가 너무 적으면 매칭 결과의 설명력이 떨어질 수 있습니다.",
    }

    card_2 = {
        "idea_title": "결과표 정리 및 데이터 시각화 자동화",
        "problem": "분석결과표 작성과 시각화 작업이 수작업 중심으로 반복됩니다.",
        "evidence_from_work_materials": repeated_work[:3] or ["분석결과표 작성", "시각화"],
        "linked_education_topics": topics[:5] or ["데이터 시각화", "workflow automation"],
        "applicable_data_or_documents": assets,
        "expected_effect": "표·그래프 산출 시간을 단축하고 재현 가능한 분석 체계를 구축합니다.",
        "implementation_difficulty": "낮음",
        "mvp_scope": "정해진 입력 컬럼 기준 결과표 자동 생성, 기본 시각화 이미지 생성",
        "future_expansion": "대시보드 연동 및 연도별 추세 자동 비교 기능 추가",
        "risk_or_limitation": "원본 데이터 스키마가 자주 바뀌면 규칙 유지보수가 필요합니다.",
    }

    card_3 = {
        "idea_title": "업무 문서검색 기반 지식관리(RAG/VectorDB) 체계",
        "problem": "기존 연구자료 검색이 비효율적이라 유사 과제 참고에 시간이 걸립니다.",
        "evidence_from_work_materials": automation_candidates[:4] or ["문서검색", "RAG", "VectorDB"],
        "linked_education_topics": topics[:6] or ["RAG", "VectorDB", "지식관리"],
        "applicable_data_or_documents": assets,
        "expected_effect": "필요한 문서·근거를 빠르게 찾고 재사용률을 높일 수 있습니다.",
        "implementation_difficulty": "높음",
        "mvp_scope": "보고서/발표자료 텍스트 색인 및 질의응답 형태의 검색 인터페이스 구현",
        "future_expansion": "권한 기반 접근 제어와 부서 간 지식 공유 기능 확장",
        "risk_or_limitation": "민감정보 마스킹·접근권한 관리 정책이 선행되어야 합니다.",
    }

    return [card_1, card_2, card_3]


def _format_evidence_label(year: str, title: str) -> str:
    if year == "미상":
        return f"과제명: {title}"
    return f"{year}년 과제: {title}"


def generate_idea_cards(
    education_concepts_path: Path,
    department_map_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    education_data = load_json(education_concepts_path) if education_concepts_path.exists() else {}
    department_data = load_json(department_map_path) if department_map_path.exists() else {}

    topics = _to_string_list(education_data.get("core_topics", [])) if isinstance(education_data, dict) else []
    repeated_work = _to_string_list(department_data.get("repeated_work_patterns", [])) if isinstance(department_data, dict) else []
    data_assets = _to_string_list(department_data.get("data_assets", [])) if isinstance(department_data, dict) else []
    automation_candidates = (
        _to_string_list(department_data.get("automation_candidates", [])) if isinstance(department_data, dict) else []
    )

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

    cards = _build_default_cards(topics, repeated_work, data_assets, automation_candidates, evidence)
    json_path = write_json(output_dir / "idea_cards.json", cards)

    lines: list[str] = ["# AI 활용 아이디어 카드", ""]
    for idx, card in enumerate(cards, start=1):
        lines.append(f"## {idx}. {card['idea_title']}")
        lines.append(f"- 문제: {card['problem']}")
        lines.append(
            "- 업무자료 근거: "
            + ", ".join(str(x) for x in card["evidence_from_work_materials"])
        )
        lines.append(
            "- 연결된 교육내용: "
            + ", ".join(str(x) for x in card["linked_education_topics"])
        )
        lines.append(
            "- 적용 가능한 자료: "
            + ", ".join(str(x) for x in card["applicable_data_or_documents"])
        )
        lines.append(f"- 기대효과: {card['expected_effect']}")
        lines.append(f"- 구현 난이도: {card['implementation_difficulty']}")
        lines.append(f"- MVP 범위: {card['mvp_scope']}")
        lines.append(f"- 향후 확장: {card['future_expansion']}")
        lines.append(f"- 한계 및 유의사항: {card['risk_or_limitation']}")
        lines.append("")

    md_path = write_utf8(output_dir / "idea_cards.md", "\n".join(lines).strip() + "\n")
    return {"idea_cards_json": json_path, "idea_cards_md": md_path}
