from __future__ import annotations

import os
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


def load_env_file(path: Path) -> bool:
    if not path.exists():
        return False

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        os.environ[key] = value
        loaded = True

    return loaded


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
