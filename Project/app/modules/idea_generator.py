from __future__ import annotations

import json
import re
from pathlib import Path

from app.llm_client import LLMClient
from app.utils.analysis_meta import build_analysis_meta, render_analysis_meta_block
from app.utils.file_utils import write_utf8
from app.utils.json_utils import load_json, write_json


BAN_TITLES = [
    "교육내용-업무자료 연계 AI 활용 아이디어 진단 도구",
    "업무 자동화 후보 탐색",
    "AI 활용 아이디어 발굴",
    "RAG",
    "VectorDB",
    "AI Agent",
    "단순 보고서 초안 생성",
    "단순 데이터 시각화",
]


AMR_TERMS = ["항생제", "내성", "amr", "mlst", "wgs", "병원체", "유전체", "plasmid", "ast", "cgmlst", "snp"]
MRSA_TERMS = ["s. aureus", "staphylococcus aureus", "mrsa", "연구동향", "문헌", "논문", "pubmed", "초록"]
NTIS_TERMS = ["ntis", "과제", "연구목표", "연구내용", "기대효과", "과제명"]
REPORT_TERMS = ["보고서", "요약", "정리", "발표자료", "문서", "행정", "검토"]


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


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _join_texts(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _score_priority(card: dict[str, object], signals: dict[str, object]) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    domain_terms = [str(x).lower() for x in _to_string_list(card.get("domain_terms", []))]
    text_blob = str(signals.get("text_blob", "")).lower()
    repeated_work = _to_string_list(signals.get("repeated_work", []))
    data_assets = _to_string_list(signals.get("data_assets", []))
    report_burden = _to_string_list(signals.get("report_burden", []))
    project_count = int(signals.get("project_count", 0) or 0)

    domain_hits = sum(1 for term in domain_terms if term and term in text_blob)
    if domain_hits >= 3:
        score += 3
        reasons.append("도메인 적합성 높음")
    elif domain_hits >= 1:
        score += 2
        reasons.append("도메인 키워드 일부 일치")
    else:
        score += 1
        reasons.append("도메인 일반 적합")

    work_terms = _to_string_list(card.get("work_terms", []))
    repeated_hits = sum(1 for item in repeated_work if any(term.lower() in item.lower() for term in work_terms))
    if repeated_hits >= 2:
        score += 2
        reasons.append("반복 업무성 높음")
    elif repeated_hits >= 1:
        score += 1
        reasons.append("반복 업무와 일부 연결")

    input_terms = _to_string_list(card.get("input_terms", []))
    asset_hits = sum(1 for item in data_assets if any(term.lower() in item.lower() for term in input_terms))
    if asset_hits >= 2:
        score += 2
        reasons.append("입력자료 확보 가능")
    elif asset_hits >= 1:
        score += 1
        reasons.append("입력자료 일부 확보")

    burden_terms = _to_string_list(card.get("burden_terms", []))
    burden_hits = sum(1 for item in report_burden if any(term.lower() in item.lower() for term in burden_terms))
    if burden_hits >= 1:
        score += 2
        reasons.append("보고·행정 부담 감소 효과 큼")

    difficulty = str(card.get("execution_difficulty", "중간"))
    if difficulty in {"낮음", "중간"}:
        score += 1
        reasons.append("MVP 구현 가능")

    if project_count >= 50 and any(term in domain_terms for term in NTIS_TERMS):
        score += 1
        reasons.append("NTIS 축적 과제 활용 가능")

    return score, "; ".join(reasons)


def _priority_label(score: int) -> str:
    if score >= 8:
        return "높음"
    if score >= 5:
        return "중간"
    return "낮음"


def _make_card(
    *,
    idea_name: str,
    applied_work: str,
    current_problem: str,
    ai_method: str,
    input_data: list[str],
    expected_output: list[str],
    expected_effect: str,
    execution_difficulty: str,
    why_fit_dept: str,
    first_step: str,
    evidence_keywords: list[str],
    related_projects: list[str],
    domain_terms: list[str],
    work_terms: list[str],
    input_terms: list[str],
    burden_terms: list[str],
    linked_topics: list[str],
    risk_or_limitation: str,
) -> dict[str, object]:
    return {
        "idea_name": idea_name,
        "applied_work": applied_work,
        "current_problem": current_problem,
        "ai_method": ai_method,
        "input_data": input_data,
        "expected_output": expected_output,
        "expected_effect": expected_effect,
        "execution_difficulty": execution_difficulty,
        "why_fit_dept": why_fit_dept,
        "first_step": first_step,
        "evidence_keywords": evidence_keywords,
        "related_projects": related_projects,
        "domain_terms": domain_terms,
        "work_terms": work_terms,
        "input_terms": input_terms,
        "burden_terms": burden_terms,
        "linked_education_topics": linked_topics,
        "risk_or_limitation": risk_or_limitation,
    }


def _domain_templates(signals: dict[str, object]) -> list[dict[str, object]]:
    topics = _to_string_list(signals.get("topics", []))
    repeated_work = _to_string_list(signals.get("repeated_work", []))
    data_assets = _to_string_list(signals.get("data_assets", []))
    evidence_keywords = _to_string_list(signals.get("evidence_keywords", []))
    related_projects = _to_string_list(signals.get("related_projects", []))
    project_count = int(signals.get("project_count", 0) or 0)
    text_blob = str(signals.get("text_blob", "")).lower()

    cards: list[dict[str, object]] = []

    amr_present = _contains_any(text_blob, AMR_TERMS) or _contains_any(" ".join(topics + repeated_work + data_assets), AMR_TERMS)
    mrsa_present = _contains_any(text_blob, MRSA_TERMS) or _contains_any(" ".join(topics + repeated_work + related_projects), MRSA_TERMS)
    ntis_heavy = project_count >= 50 or (project_count >= 20 and _contains_any(text_blob, NTIS_TERMS))

    if amr_present:
        cards.extend(
            [
                _make_card(
                    idea_name="항생제 내성균 WGS 분석결과 자동 해석·보고서 생성 도구",
                    applied_work="항생제 내성균 유전체 감시",
                    current_problem="AMR gene, MLST, plasmid, virulence, cgMLST, SNP 결과가 여러 파일로 흩어져 있어 해석과 보고서 작성이 반복됩니다.",
                    ai_method="분석결과 TSV/CSV를 통합해 핵심 내성 유전자, ST/clone, 검토 필요 샘플, 전년 대비 변화, 보고서 문장 초안을 자동 정리",
                    input_data=["AMRFinderPlus 결과", "MLST 결과", "cgMLST/SNP 결과", "plasmidfinder 결과", "virulence gene 결과", "AST 결과", "sample metadata"],
                    expected_output=["샘플별 요약표", "주요 clone 요약", "검토 필요 isolate 목록", "보고서 초안"],
                    expected_effect="분석결과 해석과 보고서 작성 시간을 줄이고 반복 검토 누락을 줄입니다.",
                    execution_difficulty="높음",
                    why_fit_dept="항생제 내성 감시와 WGS 결과 해석이 반복되는 부서 업무와 직접 연결됩니다.",
                    first_step="최근 10개 isolate의 AMR/MLST 결과를 샘플별로 하나의 표준 포맷으로 묶습니다.",
                    evidence_keywords=["항생제 내성균 유전체 감시", "유전체 분석", "WGS", "MLST", "AMR gene", "병원체"],
                    related_projects=related_projects[:3],
                    domain_terms=AMR_TERMS + ["항생제 내성균 유전체 감시", "유전체 분석", "WGS", "MLST", "AMR gene"],
                    work_terms=["보고서 작성", "유전체 분석", "표준화", "검토"],
                    input_terms=["AMRFinderPlus", "MLST", "cgMLST", "SNP", "plasmidfinder", "AST"],
                    burden_terms=["보고서", "해석", "검토"],
                    linked_topics=topics[:6],
                    risk_or_limitation="샘플 메타데이터와 결과 포맷이 달라지면 템플릿 유지보수가 필요합니다.",
                ),
                _make_card(
                    idea_name="AMR 감시자료 기반 내성률·항생제 사용량 변화 자동 요약 도구",
                    applied_work="항생제 내성 감시자료 분석",
                    current_problem="연도별, 지역별, 항생제 계열별 내성률과 사용량 변화 해석이 반복적이고 보고서 작성 부담이 큽니다.",
                    ai_method="내성률·사용량 표를 읽어 증가·감소 추세, 이상 변화, 주요 균종·항생제 조합을 자동 요약",
                    input_data=["연도별 내성률", "항생제 사용량", "균종", "지역", "항생제 계열", "AST 결과"],
                    expected_output=["변화 요약문", "경고 지표", "그래프 설명문", "정책 보고용 문장"],
                    expected_effect="정기 감시보고서 작성과 변화 해석 시간을 단축합니다.",
                    execution_difficulty="중간",
                    why_fit_dept="감시자료 정리와 분석 결과 보고가 반복되는 업무에 적합합니다.",
                    first_step="최근 3개 연도의 내성률·사용량 표를 같은 열 구조로 맞춰 입력합니다.",
                    evidence_keywords=["항생제 사용량", "내성률", "감시자료 정리", "분석결과표 작성"],
                    related_projects=related_projects[:3],
                    domain_terms=AMR_TERMS + ["내성률", "항생제 사용량", "감시자료", "AST"],
                    work_terms=["감시", "보고서", "분석결과표 작성", "정리"],
                    input_terms=["내성률", "항생제 사용량", "AST", "감시자료"],
                    burden_terms=["보고서", "해석", "정리"],
                    linked_topics=topics[:5],
                    risk_or_limitation="정책/연도별 기준이 바뀌면 비교 기준을 함께 관리해야 합니다.",
                ),
                _make_card(
                    idea_name="병원체 유전체 분석 파이프라인 QC 점검 보조 도구",
                    applied_work="WGS 분석 품질관리",
                    current_problem="species 확인, assembly 품질, contig 수, MLST, AMR gene, plasmid 결과를 사람이 반복 확인해야 합니다.",
                    ai_method="결과 파일을 기준으로 PASS/WARN/FAIL을 자동 부여하고, 검토 필요 샘플의 이유를 설명",
                    input_data=["seqkit stats", "assembly stats", "species ID", "MLST", "AMRFinderPlus", "plasmidfinder", "virulence result"],
                    expected_output=["QC summary", "재분석 필요 샘플 목록", "이상 사유 설명"],
                    expected_effect="분석 QC 표준화와 검토 시간 단축에 도움이 됩니다.",
                    execution_difficulty="중간",
                    why_fit_dept="WGS 결과 검토와 품질 확인이 반복되는 업무에 맞습니다.",
                    first_step="샘플별 QC 체크리스트를 PASS/WARN/FAIL 규칙으로 먼저 정리합니다.",
                    evidence_keywords=["WGS", "유전체 분석", "품질관리", "표준화"],
                    related_projects=related_projects[:3],
                    domain_terms=AMR_TERMS + ["품질관리", "assembly", "contig", "species", "pipeline"],
                    work_terms=["검토", "품질관리", "표준화", "분석"],
                    input_terms=["seqkit", "assembly", "MLST", "AMRFinderPlus", "plasmidfinder"],
                    burden_terms=["검토", "분석", "품질관리"],
                    linked_topics=topics[:5],
                    risk_or_limitation="QC 기준이 프로젝트마다 다르면 규칙 세트를 분리해야 합니다.",
                ),
            ]
        )

    if mrsa_present:
        cards.append(
            _make_card(
                idea_name="S. aureus/MRSA 최신 연구동향 자동 수집·분류·보고 시스템",
                applied_work="항생제내성균 연구동향 파악 및 연구모임 보고",
                current_problem="MRSA/S. aureus 관련 논문이 많아 사람이 직접 선별·분류·요약하기 어렵고 연구모임 보고서 작성이 반복됩니다.",
                ai_method="논문 초록/검색결과를 내성기전, 역학, 치료제, 진단, 유전체, 병원감염 주제로 자동 분류하고 요약",
                input_data=["PubMed 검색결과", "논문 초록", "DOI/PMID", "키워드", "기존 연구모임 보고서 양식"],
                expected_output=["월간 연구동향 보고서", "중요 논문 Top 10", "주제별 요약", "국내 감시업무 시사점"],
                expected_effect="최신 연구동향 파악과 보고서 작성 시간을 줄입니다.",
                execution_difficulty="중간",
                why_fit_dept="MRSA/S. aureus 관련 최신 동향 정리와 연구보고가 반복되는 업무에 맞습니다.",
                first_step="최근 1개월 PubMed 검색식과 분류 주제를 먼저 고정합니다.",
                evidence_keywords=["S. aureus/MRSA 연구동향", "논문", "문헌", "연구동향", "발표자료"],
                related_projects=related_projects[:3],
                domain_terms=MRSA_TERMS + ["S. aureus", "MRSA", "연구동향"],
                work_terms=["문헌조사", "발표자료 작성", "연구성과 정리", "보고서 작성"],
                input_terms=["PubMed", "논문 초록", "PMID", "DOI"],
                burden_terms=["보고서", "문헌조사", "정리"],
                linked_topics=topics[:6],
                risk_or_limitation="논문 초록만으로는 세부 결과 해석이 제한될 수 있습니다.",
            )
        )

    if ntis_heavy:
        cards.append(
            _make_card(
                idea_name="NTIS/내부보고서 기반 유사 과제·연계 가능 과제 탐색 도구",
                applied_work="연구과제 기획 및 유사 과제 검토",
                current_problem="과제 수가 많아 연도별 유사 과제, 중복 가능 주제, 연계 가능한 연구를 찾기 어렵습니다.",
                ai_method="과제명, 연구목표, 주요내용, 결과, 키워드를 기반으로 유사 과제를 묶고 연도별 흐름을 요약",
                input_data=["NTIS CSV", "내부 과제목록", "연구결과보고서", "키워드"],
                expected_output=["유사 과제 클러스터", "연도별 과제 흐름", "중복 가능 과제 목록", "신규 기획 참고자료"],
                expected_effect="과제 기획과 검토 시간을 줄이고 기존 연구성과 재활용 가능성을 높입니다.",
                execution_difficulty="중간",
                why_fit_dept="과제가 많이 쌓인 부서에서 기획·검토 업무에 직접 도움이 됩니다.",
                first_step="과제명과 연구목표를 연도별로 묶어 유사도 기준을 먼저 정합니다.",
                evidence_keywords=["NTIS 과제", "연구목표", "주요 연구내용", "중복 가능 과제"],
                related_projects=related_projects[:5],
                domain_terms=NTIS_TERMS + ["유사 과제", "과제 기획"],
                work_terms=["과제", "기획", "검토", "연구성과 정리"],
                input_terms=["NTIS CSV", "연구결과보고서", "키워드", "과제목록"],
                burden_terms=["기획", "검토", "정리"],
                linked_topics=topics[:6],
                risk_or_limitation="NTIS 원문과 내부 과제 데이터의 필드 정합성이 필요합니다.",
            )
        )

    if not cards:
        cards.extend(
            [
                _make_card(
                    idea_name="반복 문서 검토 결과 자동 정리 도구",
                    applied_work="보고서 검토와 자료 정리",
                    current_problem="반복적인 문서 검토와 정리 작업에 시간이 많이 듭니다.",
                    ai_method="문서에서 핵심 문장과 표를 뽑아 요약과 체크리스트를 자동 구성",
                    input_data=["보고서", "발표자료", "정리 대상 문서"],
                    expected_output=["요약문", "체크리스트", "검토 포인트"],
                    expected_effect="반복 검토 시간을 줄이고 누락을 줄입니다.",
                    execution_difficulty="낮음",
                    why_fit_dept="문서 검토가 많은 부서에서 빠르게 적용할 수 있습니다.",
                    first_step="가장 자주 보는 문서 한 종류를 먼저 템플릿화합니다.",
                    evidence_keywords=["보고서", "발표자료", "문서"],
                    related_projects=related_projects[:3],
                    domain_terms=REPORT_TERMS,
                    work_terms=["보고서", "정리", "검토"],
                    input_terms=["보고서", "발표자료"],
                    burden_terms=["보고서", "정리", "검토"],
                    linked_topics=topics[:4],
                    risk_or_limitation="업무 서식이 다양하면 템플릿 분리가 필요합니다.",
                ),
                _make_card(
                    idea_name="데이터 품질 점검 보조 도구",
                    applied_work="데이터 표준화와 품질 확인",
                    current_problem="데이터 형식과 누락 항목을 반복 확인해야 합니다.",
                    ai_method="필수 열 누락, 중복, 형식 불일치를 자동 점검해 경고 목록 생성",
                    input_data=["CSV", "엑셀", "표준 양식"],
                    expected_output=["품질 점검 결과", "경고 목록", "정리 가이드"],
                    expected_effect="품질 점검 시간을 줄이고 입력 오류를 줄입니다.",
                    execution_difficulty="낮음",
                    why_fit_dept="반복 입력과 정리가 있는 부서에 바로 적용하기 쉽습니다.",
                    first_step="자주 쓰는 데이터 양식의 필수 열부터 정의합니다.",
                    evidence_keywords=["데이터 정리", "표준화", "검토"],
                    related_projects=related_projects[:3],
                    domain_terms=REPORT_TERMS + ["데이터", "표준화"],
                    work_terms=["정리", "표준화", "검토"],
                    input_terms=["CSV", "엑셀", "표준 양식"],
                    burden_terms=["정리", "검토"],
                    linked_topics=topics[:4],
                    risk_or_limitation="표준 양식이 안정적이어야 규칙이 유지됩니다.",
                ),
                _make_card(
                    idea_name="최신 연구문헌 선별·요약 보조 도구",
                    applied_work="연구동향 조사와 보고",
                    current_problem="논문과 보고서가 많아 최신 자료를 추려서 요약하는 데 시간이 걸립니다.",
                    ai_method="검색 결과를 주제별로 분류하고 핵심 문장만 추출해 요약",
                    input_data=["논문 초록", "키워드", "검색결과"],
                    expected_output=["주제별 요약", "중요 문헌 목록", "보고용 한줄 요약"],
                    expected_effect="문헌 조사와 연구보고 작성 시간을 줄입니다.",
                    execution_difficulty="중간",
                    why_fit_dept="문헌조사와 연구동향 정리가 반복되는 업무에 맞습니다.",
                    first_step="최근 검색식 1개를 고정해 자동 분류 기준을 맞춥니다.",
                    evidence_keywords=["문헌조사", "연구동향", "논문"],
                    related_projects=related_projects[:3],
                    domain_terms=MRSA_TERMS + REPORT_TERMS,
                    work_terms=["문헌조사", "연구동향", "보고서"],
                    input_terms=["논문", "키워드", "검색결과"],
                    burden_terms=["문헌조사", "보고서", "정리"],
                    linked_topics=topics[:4],
                    risk_or_limitation="초록만으로는 본문 세부 해석이 제한될 수 있습니다.",
                ),
            ]
        )

    scored_cards: list[dict[str, object]] = []
    for card in cards:
        score, reason = _score_priority(card, signals)
        enriched = dict(card)
        enriched["priority_score"] = score
        enriched["priority_reason"] = reason
        enriched["priority"] = _priority_label(score)
        scored_cards.append(enriched)

    return sorted(scored_cards, key=lambda item: int(item.get("priority_score", 0) or 0), reverse=True)


def _normalize_llm_card(card: dict[str, object], fallback_topics: list[str], fallback_assets: list[str], fallback_projects: list[str]) -> dict[str, object]:
    title = str(card.get("idea_name") or card.get("idea_title") or "").strip()
    if not title:
        return {}
    if any(term.lower() in title.lower() for term in BAN_TITLES):
        return {}

    input_data = _to_string_list(card.get("input_data", card.get("applicable_data_or_documents", []))) or fallback_assets[:4]
    expected_output = _to_string_list(card.get("expected_output", [])) or _to_string_list(card.get("mvp_scope", [])) or ["업무 개선 산출물"]
    evidence_keywords = _to_string_list(card.get("evidence_keywords", [])) or fallback_projects[:3]
    related_projects = _to_string_list(card.get("related_projects", [])) or fallback_projects[:3]
    linked_topics = _to_string_list(card.get("linked_education_topics", [])) or fallback_topics[:4]

    return {
        "idea_name": title,
        "applied_work": str(card.get("applied_work", card.get("current_problem", ""))).strip() or "업무 개선",
        "current_problem": str(card.get("current_problem", card.get("problem", ""))).strip() or "업무 문제를 정리하지 못했습니다.",
        "ai_method": str(card.get("ai_method", card.get("implementation_mode", ""))).strip() or "업무 자료를 구조화해 분석합니다.",
        "input_data": input_data,
        "expected_output": expected_output,
        "expected_effect": str(card.get("expected_effect", card.get("benefit", ""))).strip() or "업무 시간을 줄입니다.",
        "execution_difficulty": str(card.get("execution_difficulty", card.get("implementation_difficulty", "중간"))).strip() or "중간",
        "why_fit_dept": str(card.get("why_fit_dept", card.get("fit_reason", ""))).strip() or "부서 업무에 적용 가능합니다.",
        "first_step": str(card.get("first_step", card.get("mvp_scope", ""))).strip() or "입력자료와 양식을 먼저 정리합니다.",
        "evidence_keywords": evidence_keywords,
        "related_projects": related_projects,
        "linked_education_topics": linked_topics,
        "risk_or_limitation": str(card.get("risk_or_limitation", card.get("limitation", ""))).strip() or "입력자료 품질에 따라 결과가 달라질 수 있습니다.",
        "domain_terms": _to_string_list(card.get("domain_terms", [])),
        "work_terms": _to_string_list(card.get("work_terms", [])),
        "input_terms": _to_string_list(card.get("input_terms", [])),
        "burden_terms": _to_string_list(card.get("burden_terms", [])),
    }


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
    related_projects = _to_string_list(department_data.get("related_projects", [])) if isinstance(department_data, dict) else []
    project_count = int(department_data.get("project_count", 0) or 0) if isinstance(department_data, dict) else 0

    text_blob = _join_texts(
        topics,
        repeated_work,
        data_assets,
        automation_candidates,
        work_areas,
        evidence_keywords,
        ai_opportunity_types,
        suggested_use_cases,
        related_projects,
    )
    signals = {
        "topics": topics,
        "repeated_work": repeated_work,
        "data_assets": data_assets,
        "automation_candidates": automation_candidates,
        "work_areas": work_areas,
        "evidence_keywords": evidence_keywords,
        "ai_opportunity_types": ai_opportunity_types,
        "suggested_use_cases": suggested_use_cases,
        "related_projects": related_projects,
        "project_count": project_count,
        "text_blob": text_blob,
        "report_burden": repeated_work + evidence_keywords + suggested_use_cases,
    }

    llm_used = False
    fallback_reason = "LLM 미사용"

    cards: list[dict[str, object]] = []
    if llm_client is not None and llm_client.can_use_idea_cards():
        system_prompt = _load_prompt_text(
            "idea_cards_system.txt",
            "교육내용과 업무자료를 연결해 아이디어 카드를 생성하는 시스템 프롬프트입니다.",
        )
        user_prompt = "\n".join(
            [
                "기술명 중심으로 제안하지 말고, 실제 부서 업무에서 바로 시도할 수 있는 업무 개선 과제로 제안하라.",
                "RAG, VectorDB, AI Agent는 아이디어명이 아니라 적용 방식 또는 구현 방법에만 포함하라.",
                "우선 추진 아이디어는 항생제내성, 병원체 유전체, WGS, MLST, AMR gene, S. aureus/MRSA, 연구동향 보고, NTIS 과제관리 등 사용자의 실제 업무 맥락과 연결하라.",
                "교육내용-업무자료 연계 AI 활용 아이디어 진단 도구는 추천하지 말라.",
                "다음 자료를 바탕으로 JSON 배열로 3개의 아이디어 카드를 작성하라.",
                "각 카드에는 아이디어명, 적용 업무, 현재 업무 문제, AI 적용 방식, 필요한 입력자료, 예상 산출물, 기대효과, 구현 난이도, 우선순위, 이 부서에 적합한 이유, 첫 실행 단계, 근거 키워드 또는 관련 과제 예시를 포함하라.",
                "근거에는 실제 업무 키워드와 실제 데이터 자산을 사용하라.",
                "입력 데이터:",
                json.dumps(signals, ensure_ascii=False, indent=2),
            ]
        )
        response = llm_client.chat(system_prompt, user_prompt).strip()
        parsed_cards: list[dict[str, object]] = []
        if response:
            try:
                data = json.loads(_clean_json_text(response))
                if isinstance(data, list):
                    parsed_cards = [_normalize_llm_card(item, topics, data_assets, related_projects) for item in data if isinstance(item, dict)]
                elif isinstance(data, dict):
                    maybe_cards = data.get("cards", [])
                    if isinstance(maybe_cards, list):
                        parsed_cards = [_normalize_llm_card(item, topics, data_assets, related_projects) for item in maybe_cards if isinstance(item, dict)]
            except Exception:
                parsed_cards = []

        parsed_cards = [card for card in parsed_cards if card]
        if parsed_cards:
            cards = parsed_cards
            llm_used = True
            fallback_reason = ""

    if not cards:
        cards = _domain_templates(signals)

    if len(cards) > 3:
        cards = cards[:3]

    enriched_cards: list[dict[str, object]] = []
    for card in cards:
        score, reason = _score_priority(card, signals)
        enriched = dict(card)
        enriched["priority_score"] = score
        enriched["priority_reason"] = reason
        enriched["priority"] = str(enriched.get("priority", _priority_label(score)))
        enriched["priority"] = _priority_label(score) if not str(enriched.get("priority", "")).strip() else str(enriched.get("priority"))
        enriched["근거 키워드 또는 관련 과제 예시"] = _dedupe([*enriched.get("evidence_keywords", []), *enriched.get("related_projects", [])])
        enriched_cards.append(enriched)

    analysis_meta = build_analysis_meta(
        llm_used=llm_used,
        generation_mode="LLM" if llm_used else "rule-based fallback",
        fallback_reason=fallback_reason,
        input_file_count=int(education_stats.get("input_file_count", 0) or 0),
        successful_file_count=int(education_stats.get("successful_file_count", 0) or 0),
        failed_file_count=int(education_stats.get("failed_file_count", 0) or 0),
        extracted_char_count=int(education_stats.get("total_extracted_chars", 0) or 0),
        ntis_project_count=project_count,
    )

    json_path = write_json(
        output_dir / "idea_cards.json",
        {
            "generated_with_llm": llm_used,
            "fallback_reason": fallback_reason,
            "analysis_meta": analysis_meta,
            "cards": enriched_cards,
        },
    )

    lines: list[str] = ["# AI 활용 아이디어 카드", "", render_analysis_meta_block(analysis_meta).strip(), ""]
    if not llm_used:
        lines.extend(["- LLM 미사용으로 인해 아이디어 품질이 제한될 수 있음", ""])

    for idx, card in enumerate(enriched_cards, start=1):
        lines.append(f"## {idx}. {card['idea_name']}")
        lines.append(f"- 적용 업무: {card['applied_work']}")
        lines.append(f"- 현재 업무 문제: {card['current_problem']}")
        lines.append(f"- AI 적용 방식: {card['ai_method']}")
        lines.append("- 필요한 입력자료: " + ", ".join(str(x) for x in _to_string_list(card.get("input_data", []))))
        lines.append("- 예상 산출물: " + ", ".join(str(x) for x in _to_string_list(card.get("expected_output", []))))
        lines.append(f"- 기대효과: {card['expected_effect']}")
        lines.append(f"- 구현 난이도: {card['execution_difficulty']}")
        lines.append(f"- 우선순위: {card['priority']}")
        lines.append(f"- 이 부서에 적합한 이유: {card['why_fit_dept']}")
        lines.append(f"- 첫 실행 단계: {card['first_step']}")
        lines.append("- 근거 키워드 또는 관련 과제 예시: " + ", ".join(str(x) for x in _to_string_list(card.get("근거 키워드 또는 관련 과제 예시", []))))
        lines.append(f"- 한계 및 유의사항: {card['risk_or_limitation']}")
        lines.append("")

    md_path = write_utf8(output_dir / "idea_cards.md", "\n".join(lines).strip() + "\n")
    return {"idea_cards_json": json_path, "idea_cards_md": md_path}
