from __future__ import annotations

from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_analysis_meta(
    *,
    llm_used: bool,
    generation_mode: str,
    fallback_reason: str = "",
    input_file_count: int = 0,
    successful_file_count: int = 0,
    failed_file_count: int = 0,
    extracted_char_count: int = 0,
    ntis_project_count: int = 0,
    last_llm_error: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "created_at": now_iso(),
        "llm_used": bool(llm_used),
        "generation_mode": generation_mode,
        "fallback_reason": fallback_reason,
        "input_file_count": int(input_file_count),
        "successful_file_count": int(successful_file_count),
        "failed_file_count": int(failed_file_count),
        "extracted_char_count": int(extracted_char_count),
        "ntis_project_count": int(ntis_project_count),
        "last_llm_error": last_llm_error,
    }
    if extra:
        meta.update(extra)
    return meta


def render_analysis_meta_block(meta: dict[str, Any]) -> str:
    lines = ["## 분석 메타정보", ""]
    created_at = str(meta.get("created_at", ""))
    lines.append(f"- 생성일시: {created_at}")
    lines.append(f"- LLM 사용: {'예' if meta.get('llm_used') else '아니오'}")
    lines.append(f"- 생성 방식: {meta.get('generation_mode', 'unknown')}")
    fallback_reason = str(meta.get("fallback_reason", "")).strip() or "없음"
    lines.append(f"- fallback 사유: {fallback_reason}")
    lines.append(f"- 입력파일 수: {int(meta.get('input_file_count', 0) or 0)}개")
    lines.append(f"- 성공 추출 파일 수: {int(meta.get('successful_file_count', 0) or 0)}개")
    lines.append(f"- 실패 파일 수: {int(meta.get('failed_file_count', 0) or 0)}개")
    lines.append(f"- 교육자료 추출 글자 수: {int(meta.get('extracted_char_count', 0) or 0)}자")
    lines.append(f"- NTIS 과제 수: {int(meta.get('ntis_project_count', 0) or 0)}건")
    last_error = str(meta.get("last_llm_error", "")).strip() or "없음"
    lines.append(f"- 마지막 LLM 오류: {last_error}")
    return "\n".join(lines) + "\n"
