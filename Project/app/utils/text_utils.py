from __future__ import annotations

from pathlib import Path

from app.utils.file_utils import read_utf8


def merge_documents(paths: list[Path]) -> str:
    merged: list[str] = []
    for path in paths:
        content = read_utf8(path).strip()
        if not content:
            continue
        merged.append(f"## Source: {path.name}\n\n{content}")
    return "\n\n---\n\n".join(merged)


def clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]
