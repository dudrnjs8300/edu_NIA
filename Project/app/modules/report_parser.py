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
    return " ".join(value.strip() for value in values if value and value.strip())


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
        ai_keywords = [
            "자동 요약",
            "문서검색",
            "RAG",
            "VectorDB",
            "보고서 초안 생성",
            "결과표 정리",
            "데이터 시각화",
            "연구성과 지식맵",
            "과제 유사도 검색",
            "업무 자동화 후보 탐색",
            "AI 아이디어 진단",
            "데이터 표준화 지원",
            "교육결과 보고서 초안 생성",
        ]
        if not (repeated_tasks or data_types):
            ai_keywords = []

        rows.append(
            {
                "source_file": source_file,
                "source_type": _source_type_for_csv(),
                "year": year,
                "project_id": _csv_get(row, "과제고유번호"),
                "project_title": project_title,
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
                "repeated_tasks": repeated_tasks,
                "data_types": data_types,
                "ai_opportunity_keywords": ai_keywords,
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

        ai_keywords: list[str] = []
        if repeated_tasks or data_types:
            ai_keywords = _dedupe_preserve_order(AI_OPPORTUNITY_POOL)

        row = {
            "source_file": file_path.name,
            "source_type": _source_type_for_md(),
            "year": _extract_year(file_path.name, content),
            "project_title": project_title,
            "objective": objective,
            "main_contents": main_contents,
            "methods": methods,
            "results": results,
            "outputs": outputs,
            "research_keywords": [],
            "repeated_tasks": repeated_tasks,
            "data_types": data_types,
            "ai_opportunity_keywords": ai_keywords,
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
