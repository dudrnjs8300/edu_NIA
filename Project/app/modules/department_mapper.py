from __future__ import annotations

from collections import Counter
import re
from pathlib import Path

from app.utils.file_utils import write_utf8
from app.utils.json_utils import load_jsonl, write_json


def _dedupe_limit(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if limit is not None and len(result) >= limit:
            break
    return result


def _year_sort_key(year: str) -> tuple[int, str]:
    return (1 if year == "미상" else 0, year)


def _bullets(items: list[str], *, default: str = "정보 없음", indent: str = "- ") -> list[str]:
    if not items:
        return [f"{indent}{default}"]
    return [f"{indent}{item}" for item in items]


def _expand_items(items: list[str]) -> list[str]:
    expanded: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        parts = [part.strip() for part in re.split(r"\s+-\s+", text) if part.strip()]
        if len(parts) > 1:
            expanded.extend(parts)
        else:
            expanded.append(text)
    return expanded


def _token_text(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, list):
            parts.extend(str(item) for item in value if str(item).strip())
        else:
            text = str(value).strip()
            if text:
                parts.append(text)
    return " ".join(parts).lower()


def _matches_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


WORK_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["항생제", "내성", "amr", "mlst", "plasmid"], "항생제 내성균 유전체 감시"),
    (["유전체", "wgs", "전장유전체", "변이", "genome", "한국인칩"], "유전체 빅데이터 구축 및 품질관리"),
    (["병원체", "균주", "자원은행", "패널", "maldi-tof", "동정"], "병원체 자원 특성분석"),
    (["백신", "면역원성", "항원", "후보물질", "중화항체", "epitope", "에피토프"], "감염병 백신·치료 후보물질 평가"),
    (["코호트", "임상자료", "역학", "건강영향", "파킨슨", "미세먼지", "질병위험", "예측"], "임상·역학자료 기반 질병위험 예측"),
    (["오믹스", "전사체", "단일세포", "후성유전체", "단백체", "rna seq", "bcr", "tcr", "바이오마커"], "오믹스 기반 바이오마커 발굴"),
    (["데이터센터", "연구데이터", "분양", "공개", "표준화", "헬프데스크", "운영"], "보건의료 연구데이터 인프라 운영"),
    (["파이프라인", "분석지원", "coda", "정제", "통합분석", "cloud", "클라우드", "database"], "분석 파이프라인 구축"),
    (["보고서", "발표자료", "연구성과", "논문", "시각화", "자료화"], "연구성과 보고 및 자료화"),
    (["기탁", "sop", "자원 확보", "분양자원"], "데이터 표준화 및 분양체계 구축"),
    (["줄기세포", "ipsc", "오가노이드", "분화", "cell therapy", "gene editing", "car", "hla"], "줄기세포·오가노이드 모델 개발"),
]


def _derive_work_categories(row: dict[str, object]) -> list[str]:
    text = _token_text(
        row.get("project_title", ""),
        row.get("main_contents", []),
        row.get("research_keywords", []),
        row.get("data_types", []),
    )
    categories: list[str] = []
    for keywords, label in WORK_CATEGORY_RULES:
        if _matches_any(text, keywords):
            categories.append(label)

    if not categories:
        categories.append("연구성과 보고 및 자료화")

    return _dedupe_limit(categories)


def build_department_map(report_summaries_jsonl: Path, output_dir: Path) -> dict[str, Path]:
    rows = load_jsonl(report_summaries_jsonl)

    yearly: dict[str, dict[str, object]] = {}
    all_major_work_areas: list[str] = []
    all_data_assets: list[str] = []
    all_automation_candidates: list[str] = []
    repeated_work_patterns: list[str] = []
    program_values: list[str] = []
    source_types: list[str] = []
    keyword_counter: Counter[str] = Counter()

    for row in rows:
        year = str(row.get("year", "")).strip() or "미상"
        source_type = str(row.get("source_type", "")).strip() or "markdown_report"
        program_name = str(row.get("program_name", "")).strip()

        year_bucket = yearly.setdefault(
            year,
            {
                "project_count": 0,
                "project_titles": [],
                "main_work_areas": [],
                "data_assets": [],
                "automation_candidates": [],
            },
        )

        year_bucket["project_count"] = int(year_bucket["project_count"]) + 1

        project_title = str(row.get("project_title", "")).strip()
        if project_title:
            year_bucket["project_titles"].append(project_title)

        main_work_areas = _derive_work_categories(row)
        data_assets = [str(x).strip() for x in row.get("data_types", []) if str(x).strip()]
        automation_candidates = [str(x).strip() for x in row.get("ai_opportunity_keywords", []) if str(x).strip()]

        year_bucket["main_work_areas"].extend(main_work_areas)
        year_bucket["data_assets"].extend(data_assets)
        year_bucket["automation_candidates"].extend(automation_candidates)

        all_major_work_areas.extend(main_work_areas)
        repeated_work_patterns.extend([str(x).strip() for x in row.get("repeated_tasks", []) if str(x).strip()])
        all_data_assets.extend(data_assets)
        all_automation_candidates.extend(automation_candidates)

        if program_name:
            program_values.append(program_name)
        source_types.append(source_type)

        research_keywords = [str(x).strip() for x in row.get("research_keywords", []) if str(x).strip()]
        keyword_counter.update(research_keywords)

    years = _dedupe_limit(sorted(yearly.keys(), key=_year_sort_key))
    programs = _dedupe_limit(program_values, 30)
    source_types = _dedupe_limit(source_types)
    top_keywords = [keyword for keyword, _ in keyword_counter.most_common(30)]

    major_work_areas = _dedupe_limit(all_major_work_areas, 30)
    repeated_work_patterns = _dedupe_limit(repeated_work_patterns, 30)
    data_assets = _dedupe_limit(all_data_assets, 30)
    automation_candidates = _dedupe_limit(all_automation_candidates, 30)

    timeline: list[dict[str, object]] = []
    for year in sorted(yearly.keys(), key=_year_sort_key):
        info = yearly[year]
        timeline.append(
            {
                "year": year,
                "project_count": int(info["project_count"]),
                "representative_projects": _dedupe_limit(info["project_titles"], 10),
                "main_work_areas": _dedupe_limit(info["main_work_areas"], 15),
                "data_assets": _dedupe_limit(info["data_assets"], 10) or _dedupe_limit(data_assets, 10),
                "automation_candidates": _dedupe_limit(info["automation_candidates"], 10) or _dedupe_limit(automation_candidates, 10),
            }
        )

    department_work_summary = (
        f"총 {len(rows)}건의 과제를 분석했으며, "
        f"{len(years)}개 연도에서 반복 업무 {len(repeated_work_patterns)}개, "
        f"데이터 자산 {len(data_assets)}개, 자동화 후보 {len(automation_candidates)}개를 확인했습니다."
    )

    department_work_map = {
        "department_work_summary": department_work_summary,
        "project_count": len(rows),
        "years": years,
        "programs": programs,
        "source_types": source_types,
        "top_keywords": top_keywords,
        "major_work_areas": major_work_areas,
        "repeated_work_patterns": repeated_work_patterns,
        "data_assets": data_assets,
        "automation_candidates": automation_candidates,
        "timeline": timeline,
    }
    map_path = write_json(output_dir / "department_work_map.json", department_work_map)

    timeline_lines: list[str] = ["# 부서 업무 이력 요약", "", "## 전체 요약"]
    timeline_lines.append(f"- 분석 과제 수: {len(rows)}건")
    timeline_lines.append(f"- 분석 연도: {', '.join(years) if years else '정보 없음'}")
    timeline_lines.append("- 주요 업무영역:")
    timeline_lines.extend(_bullets(major_work_areas[:10], default="정보 없음", indent="  - "))
    timeline_lines.append("- 주요 데이터 자산:")
    timeline_lines.extend(_bullets(data_assets[:10], default="정보 없음", indent="  - "))
    timeline_lines.append("- 자동화 후보:")
    timeline_lines.extend(_bullets(automation_candidates[:10], default="정보 없음", indent="  - "))
    timeline_lines.append("")

    for year in sorted(yearly.keys(), key=_year_sort_key):
        item = next(entry for entry in timeline if entry["year"] == year)
        timeline_lines.append(f"## {year}")
        timeline_lines.append(f"- 과제 수: {item['project_count']}건")
        timeline_lines.append("- 대표 과제:")
        timeline_lines.extend(_bullets(item["representative_projects"], default="정보 없음", indent="  - "))
        timeline_lines.append("- 주요 업무영역:")
        timeline_lines.extend(_bullets(item["main_work_areas"], default="정보 없음", indent="  - "))
        timeline_lines.append("- 주요 데이터/자료:")
        timeline_lines.extend(_bullets(item["data_assets"], default="정보 없음", indent="  - "))
        timeline_lines.append("- 자동화 후보:")
        timeline_lines.extend(_bullets(item["automation_candidates"], default="정보 없음", indent="  - "))
        timeline_lines.append("")

    timeline_path = write_utf8(output_dir / "department_timeline.md", "\n".join(timeline_lines).strip() + "\n")
    return {
        "department_work_map": map_path,
        "department_timeline": timeline_path,
    }
