from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from app.utils.file_utils import list_text_inputs, read_utf8
from app.utils.json_utils import write_jsonl
from app.modules.document_converter import load_converted_documents


HEADING_MAP: dict[str, str] = {
    "과제명": "project_title",
    "연구목표": "objective",
    "주요 연구내용": "main_contents",
    "실험방법": "methods",
    "연구방법": "methods",
    "연구결과": "results",
    "산출물": "outputs",
}

NORMALIZED_HEADING_MAP: dict[str, str] = {
    re.sub(r"\s+", "", key).strip(): value for key, value in HEADING_MAP.items()
}

REPEATED_TASK_KEYWORDS: list[str] = [
    "보고서 작성",
    "분석결과표 작성",
    "문헌조사",
    "데이터 정리",
    "유전체 분석",
    "시각화",
    "발표자료 작성",
]

DATA_TYPE_KEYWORDS: list[str] = [
    "WGS",
    "AST",
    "MLST",
    "AMR gene",
    "plasmid",
    "genome assembly",
    "연구보고서",
    "발표자료",
    "엑셀 데이터",
]

AI_OPPORTUNITY_POOL: list[str] = [
    "자동 요약",
    "결과표 정리",
    "문서검색",
    "RAG",
    "VectorDB",
    "보고서 초안 생성",
    "데이터 시각화",
    "분류",
    "예측",
    "이상탐지",
    "자동보고",
    "질의응답",
    "문헌검색",
    "연구성과 지식맵",
    "과제 유사도 검색",
    "업무 자동화 후보 탐색",
    "AI 아이디어 진단",
    "데이터 표준화 지원",
    "교육결과 보고서 초안 생성",
]

CSV_REPEAT_KEYWORDS: list[str] = [
    "데이터 정리",
    "보고서 작성",
    "분석결과표 작성",
    "유전체 분석",
    "오믹스 분석",
    "감시자료 정리",
    "시스템 운영",
    "플랫폼 구축",
    "표준화",
    "모델 개발",
    "예측 모델 구축",
    "데이터베이스 구축",
    "교육자료 작성",
    "질의응답 지원",
    "연구성과 정리",
    "문헌조사",
    "자료 수집",
    "통계 분석",
    "시각화",
]

CSV_DATA_TYPES: list[str] = [
    "WGS",
    "유전체",
    "전장유전체",
    "MLST",
    "AMR gene",
    "plasmid",
    "오믹스",
    "단일세포",
    "전사체",
    "마이크로바이옴",
    "임상자료",
    "코호트",
    "연구데이터",
    "보건의료데이터",
    "백신",
    "병원체",
    "감염병",
    "항생제 내성",
    "항생제 사용량",
    "내성율",
    "줄기세포",
    "미세먼지",
    "후성유전체",
    "설문자료",
    "실험결과",
    "연구보고서",
    "발표자료",
]

WORK_AREA_RULES: list[tuple[list[str], str]] = [
    (["항생제", "내성", "amr"], "항생제 내성·감시"),
    (["감염병", "병원체", "균주", "백신"], "감염병·병원체 연구"),
    (["유전체", "wgs", "mlst", "plasmid"], "유전체 분석·품질관리"),
    (["코호트", "임상", "역학", "위험"], "임상·역학 분석"),
    (["오믹스", "전사체", "단일세포", "후성유전체"], "오믹스 기반 바이오마커"),
    (["데이터", "플랫폼", "표준화", "시스템", "구축"], "데이터 인프라·표준화"),
    (["보고서", "시각화", "발표", "문서"], "보고·문서화 자동화"),
]

AI_OPPORTUNITY_RULES: list[tuple[list[str], list[str]]] = [
    (["보고서", "결과", "요약"], ["자동 요약", "보고서 초안 생성", "자동보고"]),
    (["분류", "정리", "표준화"], ["분류", "데이터 표준화 지원", "결과표 정리"]),
    (["검색", "문헌", "과제"], ["문서검색", "문헌검색", "과제 유사도 검색", "RAG"]),
    (["시각화", "통계", "분석"], ["데이터 시각화", "이상탐지", "예측"]),
    (["질의응답", "질의", "응답"], ["질의응답", "업무 자동화 후보 탐색"]),
    (["감시", "추적", "평가"], ["자동보고", "예측", "이상탐지"]),
]

USE_CASE_MAP: dict[str, str] = {
    "자동 요약": "과제 설명과 연구결과를 짧게 요약해 검토 시간을 줄입니다.",
    "결과표 정리": "산재한 결과값을 표준 형식으로 모아 표와 목록을 자동 생성합니다.",
    "문서검색": "보고서와 부속 자료를 검색해 필요한 근거를 빠르게 찾습니다.",
    "RAG": "과거 과제와 보고서를 연결해 질문-응답형 지식검색을 지원합니다.",
    "VectorDB": "유사 과제와 문서 단락을 벡터 검색으로 연결합니다.",
    "보고서 초안 생성": "분석 요약을 바탕으로 보고서 초안을 만듭니다.",
    "데이터 시각화": "과제 추세와 결과를 그래프/차트로 보여줍니다.",
    "분류": "과제를 분야/병원체/데이터 유형별로 나눕니다.",
    "예측": "과제 결과나 추세를 바탕으로 향후 경향을 추정합니다.",
    "이상탐지": "비정상 패턴이나 누락 데이터를 찾아냅니다.",
    "자동보고": "정기 보고서를 자동으로 작성합니다.",
    "질의응답": "담당자가 자연어로 질문하면 관련 문서를 찾아 답합니다.",
    "문헌검색": "연구 배경과 유사 과제를 빠르게 탐색합니다.",
    "연구성과 지식맵": "과제 간 관계와 반복 주제를 시각화합니다.",
    "과제 유사도 검색": "유사 연구를 찾아 재사용과 비교를 돕습니다.",
    "업무 자동화 후보 탐색": "반복 업무를 골라 자동화 우선순위를 정합니다.",
    "AI 아이디어 진단": "교육내용과 업무자료를 연결해 적용 가능성을 점검합니다.",
    "데이터 표준화 지원": "필드명과 자료형을 맞춰 데이터 품질을 높입니다.",
    "교육결과 보고서 초안 생성": "교육성과 보고서를 빠르게 정리합니다.",
}


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def _clean_item(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[-*•○●∙ㆍ·]\s*", "", cleaned)
    cleaned = re.sub(r"[.。]\s*$", "", cleaned)
    cleaned = re.sub(r"\s*(을|를)?\s*(수행하였다|실시하였다|진행하였다|하였다)\s*$", "", cleaned)
    return cleaned.strip()


def _split_comma_items(text: str) -> list[str]:
    parts = [_clean_item(part) for part in text.split(",")]
    return [part for part in parts if len(part) >= 2]


def _split_items(text: str, *, split_commas: bool = False) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullet_items = [_clean_item(line) for line in lines if re.match(r"^[-*•○●∙ㆍ·]\s*", line)]
    bullet_items = [item for item in bullet_items if item]
    if bullet_items:
        return bullet_items

    plain_lines = [_clean_item(line) for line in lines if _clean_item(line)]
    if split_commas and plain_lines:
        combined = " ".join(plain_lines)
        if "," in combined:
            comma_items = _split_comma_items(combined)
            if comma_items:
                return comma_items

    return plain_lines


def _split_any_list(text: str, *, split_commas: bool = True) -> list[str]:
    if not text.strip():
        return []

    parts = re.split(r"[\n○●•∙ㆍ·;]", text)
    items: list[str] = []
    for part in parts:
        cleaned = _clean_item(part)
        if not cleaned:
            continue
        if split_commas and "," in cleaned:
            for piece in cleaned.split(","):
                piece = _clean_item(piece)
                if len(piece) >= 2:
                    items.append(piece)
        else:
            if len(cleaned) >= 2:
                items.append(cleaned)
    return _dedupe_preserve_order(items)


def _split_keywords(text: str) -> list[str]:
    if not text.strip():
        return []
    items = [_clean_item(part) for part in text.split(",")]
    return _dedupe_preserve_order([item for item in items if item])


def _nonempty_texts(*values: str) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _source_type_for_md() -> str:
    return "markdown_report"


def _source_type_for_csv() -> str:
    return "ntis_csv"


def _extract_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {v: [] for v in HEADING_MAP.values()}
    current_key: str | None = None

    for line in content.splitlines():
        heading_match = re.match(r"^\s{0,3}#{1,6}\s*(.+?)\s*$", line)
        if heading_match:
            heading = _normalize_heading(heading_match.group(1))
            current_key = NORMALIZED_HEADING_MAP.get(heading)
            continue

        inline_match = re.match(r"^\s*(과제명|연구목표|주요 연구내용|실험방법|연구결과|산출물)\s*[:：]\s*(.+)$", line)
        if inline_match:
            key = NORMALIZED_HEADING_MAP[_normalize_heading(inline_match.group(1))]
            sections[key].append(inline_match.group(2).strip())
            current_key = key
            continue

        if current_key:
            sections[current_key].append(line)

    joined: dict[str, str] = {}
    for key, lines in sections.items():
        joined[key] = "\n".join(lines).strip()
    return joined


def _extract_year(source_file: str, content: str) -> str:
    match = re.search(r"(19|20)\d{2}", source_file)
    if match:
        return match.group(0)
    body_match = re.search(r"(19|20)\d{2}", content)
    if body_match:
        return body_match.group(0)
    return "미상"


def _normalize_csv_row(row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[key.lstrip("\ufeff").strip()] = (value or "").strip()
    return normalized


def _csv_get(row: dict[str, str], key: str) -> str:
    return row.get(key, "").strip()


def _extract_csv_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        raw_rows = list(csv.reader(f))

    header_index = None
    for index, row in enumerate(raw_rows):
        normalized_cells = {cell.lstrip("\ufeff").strip() for cell in row}
        if {"기준년도", "과제명(국문)", "과제고유번호"} & normalized_cells:
            header_index = index
            break

    if header_index is None:
        return rows

    header = [cell.lstrip("\ufeff").strip() for cell in raw_rows[header_index]]
    for raw_row in raw_rows[header_index + 1 :]:
        if not any(cell.strip() for cell in raw_row):
            continue
        row = {header[i]: raw_row[i].strip() if i < len(raw_row) else "" for i in range(len(header))}
        row = _normalize_csv_row(row)

        source_file = csv_path.name
        year = _csv_get(row, "기준년도")
        project_title = _csv_get(row, "과제명(국문)")
        program_name = _csv_get(row, "사업명")
        subprogram_name = _csv_get(row, "내역사업명")
        pi_name = _csv_get(row, "연구책임자명")
        institution = _csv_get(row, "과제수행기관명")
        objective = _csv_get(row, "연구목표요약")
        main_contents = _split_any_list(_csv_get(row, "연구내용요약"), split_commas=True)
        results = _split_any_list(_csv_get(row, "기대효과요약"), split_commas=True)
        research_keywords = _split_keywords(_csv_get(row, "한글키워드"))
        budget_total = _csv_get(row, "연구비합계")
        budget_government = _csv_get(row, "정부투자연구비")

        combined_text = _nonempty_texts(
            project_title,
            objective,
            " ".join(main_contents),
            " ".join(results),
            " ".join(research_keywords),
        )

        repeated_tasks = [kw for kw in CSV_REPEAT_KEYWORDS if kw in combined_text]
        data_types = [kw for kw in CSV_DATA_TYPES if kw in combined_text]
        work_area = _derive_work_area(_nonempty_texts(project_title, objective, program_name, subprogram_name, research_keywords, main_contents, results))
        evidence_keywords = _derive_evidence_keywords(
            project_title,
            program_name,
            subprogram_name,
            objective,
            main_contents,
            results,
            research_keywords,
            repeated_tasks,
            data_types,
        )
        ai_keywords = _derive_ai_opportunity_types(combined_text)
        suggested_ai_use_cases = _derive_suggested_use_cases(ai_keywords)

        rows.append(
            {
                "source_file": source_file,
                "source_type": _source_type_for_csv(),
                "year": year,
                "project_id": _csv_get(row, "과제고유번호"),
                "project_title": project_title,
                "work_area": work_area,
                "program_name": program_name,
                "subprogram_name": subprogram_name,
                "pi_name": pi_name,
                "institution": institution,
                "objective": objective,
                "main_contents": main_contents,
                "methods": [],
                "results": results,
                "outputs": [],
                "research_keywords": research_keywords,
                "evidence_keywords": evidence_keywords,
                "repeated_tasks": repeated_tasks,
                "data_types": data_types,
                "ai_opportunity_keywords": ai_keywords,
                "ai_opportunity_types": ai_keywords,
                "suggested_ai_use_cases": suggested_ai_use_cases,
                "budget_total": budget_total,
                "budget_government": budget_government,
            }
        )

    return rows


def _find_keywords(content: str, keywords: list[str]) -> list[str]:
    lowered = content.lower()
    found: list[str] = []
    for keyword in keywords:
        if keyword.lower() in lowered:
            found.append(keyword)
    return found


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _derive_work_area(text: str) -> str:
    lowered = text.lower()
    for keywords, label in WORK_AREA_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return label
    return "연구성과 보고·문서화"


def _derive_ai_opportunity_types(text: str) -> list[str]:
    lowered = text.lower()
    opportunities: list[str] = []
    for keywords, labels in AI_OPPORTUNITY_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            opportunities.extend(labels)
    if not opportunities:
        opportunities = ["자동 요약", "문서검색", "보고서 초안 생성"]
    return _dedupe_preserve_order(opportunities)


def _derive_suggested_use_cases(opportunity_types: list[str]) -> list[str]:
    use_cases: list[str] = []
    for item in opportunity_types:
        description = USE_CASE_MAP.get(item)
        if description:
            use_cases.append(f"{item}: {description}")
    if not use_cases:
        use_cases = ["데이터와 보고서를 함께 정리해 업무 검색과 보고서 초안을 자동화합니다."]
    return _dedupe_preserve_order(use_cases)


def _derive_evidence_keywords(*values: object) -> list[str]:
    evidence: list[str] = []
    for value in values:
        if isinstance(value, list):
            evidence.extend(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value).strip()
            if text:
                evidence.append(text)
    return _dedupe_preserve_order(evidence)


def process_reports(input_dir: Path, output_jsonl_path: Path) -> dict[str, Path]:
    files = list_text_inputs(input_dir)
    workspace_root = output_jsonl_path.parents[1]
    doc_extract_dir = workspace_root / "02_education_processed" / "doc_extracts"
    files.extend(load_converted_documents(input_dir, doc_extract_dir))
    rows: list[dict[str, object]] = []

    for file_path in files:
        content = read_utf8(file_path)
        sections = _extract_sections(content)

        project_title = sections.get("project_title", "").strip() or file_path.stem
        objective = sections.get("objective", "").strip()
        main_contents = _split_items(sections.get("main_contents", ""))
        methods = _split_items(sections.get("methods", ""), split_commas=True)
        results = _split_items(sections.get("results", ""))
        outputs = _split_items(sections.get("outputs", ""))

        repeated_tasks = _find_keywords(content, REPEATED_TASK_KEYWORDS)
        data_types = _find_keywords(content, DATA_TYPE_KEYWORDS)
        work_area = _derive_work_area(_nonempty_texts(project_title, objective, " ".join(main_contents), " ".join(results), " ".join(outputs)))
        evidence_keywords = _derive_evidence_keywords(project_title, objective, main_contents, results, outputs, repeated_tasks, data_types)
        ai_keywords = _derive_ai_opportunity_types(_nonempty_texts(project_title, objective, " ".join(main_contents), " ".join(results), " ".join(repeated_tasks), " ".join(data_types)))
        suggested_ai_use_cases = _derive_suggested_use_cases(ai_keywords)

        row = {
            "source_file": file_path.name,
            "source_type": _source_type_for_md(),
            "year": _extract_year(file_path.name, content),
            "project_title": project_title,
            "work_area": work_area,
            "objective": objective,
            "main_contents": main_contents,
            "methods": methods,
            "results": results,
            "outputs": outputs,
            "research_keywords": [],
            "evidence_keywords": evidence_keywords,
            "repeated_tasks": repeated_tasks,
            "data_types": data_types,
            "ai_opportunity_keywords": ai_keywords,
            "ai_opportunity_types": ai_keywords,
            "suggested_ai_use_cases": suggested_ai_use_cases,
            "project_id": "",
            "program_name": "",
            "subprogram_name": "",
            "pi_name": "",
            "institution": "",
            "budget_total": "",
            "budget_government": "",
        }
        rows.append(row)

    csv_files = sorted(input_dir.parent.joinpath("03_ntis_raw").glob("*.csv"))
    for csv_path in csv_files:
        rows.extend(_extract_csv_rows(csv_path))

    jsonl_path = write_jsonl(output_jsonl_path, rows)
    return {"report_summaries_jsonl": jsonl_path}
