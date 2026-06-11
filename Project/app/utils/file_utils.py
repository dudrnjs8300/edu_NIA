from __future__ import annotations

from pathlib import Path


WORKSPACE_SUBDIRS: tuple[str, ...] = (
    "01_education_raw",
    "02_education_processed",
    "03_ntis_raw",
    "04_ntis_md",
    "05_department_analysis",
    "06_matching_output",
    "07_final_report",
)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_workspace(workspace_root: Path) -> list[Path]:
    created: list[Path] = []
    ensure_dir(workspace_root)
    for sub in WORKSPACE_SUBDIRS:
        created.append(ensure_dir(workspace_root / sub))
    return created


def list_text_inputs(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".txt", ".md"}
    ]
    return sorted(files, key=lambda p: p.name)


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_utf8(path: Path, content: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return path
