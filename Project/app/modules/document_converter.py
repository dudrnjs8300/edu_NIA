from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from app.utils.file_utils import ensure_dir, write_utf8


SUPPORTED_EXTENSIONS = {".hwpx", ".hwp"}
MANIFEST_NAME = "doc_extracts_manifest.json"
ERROR_LOG_NAME = "doc_errors.log"


@dataclass(frozen=True)
class ConvertedDocument:
    source_path: Path
    output_path: Path
    file_type: str
    status: str
    method: str


def _log_error(log_path: Path, message: str) -> None:
    ensure_dir(log_path.parent)
    previous = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    entry = message.rstrip() + "\n"
    log_path.write_text(previous + entry, encoding="utf-8")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_markdown(source_name: str, file_type: str, method: str, extracted_text: str) -> str:
    body = _normalize_text(extracted_text)
    if not body:
        body = "텍스트를 추출하지 못했습니다. Kordoc MCP 변환기 연결 또는 수동 변환이 필요합니다."

    return "\n".join(
        [
            "# 문서 변환 결과",
            "",
            f"* 원본 파일: {source_name}",
            f"* 변환 방식: {method}",
            f"* 파일 유형: {file_type}",
            "",
            "## 추출 텍스트",
            "",
            body,
            "",
        ]
    )


def convert_hwpx_with_kordoc(input_path: Path) -> str | None:
    """Placeholder connection point for a future Kordoc MCP integration.

    The current OpenCode session exposes Kordoc MCP at the tooling layer, not
    as a stable local CLI/API contract. Do not guess an invocation path here.
    Return None so the safe fallback can continue without breaking the pipeline.
    """

    _ = input_path
    return None


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _extract_text_from_xml(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""

    parts: list[str] = []
    for text in root.itertext():
        cleaned = text.strip()
        if cleaned:
            parts.append(cleaned)

    if not parts:
        return ""

    lines: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        if lines and lines[-1] == part:
            continue
        lines.append(part)
    return "\n".join(lines)


def _extract_hwpx_text_fallback(input_path: Path) -> str:
    if input_path.suffix.lower() != ".hwpx":
        return ""

    try:
        with zipfile.ZipFile(input_path) as archive:
            xml_names = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".xml") and (
                    "contents/" in name.lower() or "bodytext/" in name.lower() or "section" in name.lower()
                )
            ]
            if not xml_names:
                xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]

            extracted_blocks: list[str] = []
            for xml_name in sorted(xml_names):
                try:
                    xml_text = _extract_text_from_xml(archive.read(xml_name))
                except KeyError:
                    continue
                if xml_text:
                    extracted_blocks.append(xml_text)

            if not extracted_blocks:
                return ""

            return _normalize_text("\n\n".join(extracted_blocks))
    except zipfile.BadZipFile:
        return ""
    except Exception:
        return ""


def _write_conversion_output(
    output_path: Path,
    source_name: str,
    file_type: str,
    method: str,
    extracted_text: str,
) -> Path:
    markdown = _format_markdown(source_name, file_type, method, extracted_text)
    return write_utf8(output_path, markdown)


def _read_existing_metadata(output_path: Path) -> tuple[str, str]:
    if not output_path.exists():
        return ("", "")

    text = output_path.read_text(encoding="utf-8", errors="ignore")
    status = "success" if "텍스트를 추출하지 못했습니다" not in text else "failed"
    method = ""
    for line in text.splitlines()[:12]:
        if line.startswith("* 변환 방식:"):
            method = line.split(":", 1)[1].strip()
            break
    return status, method


def _load_manifest(manifest_path: Path) -> list[dict[str, str]]:
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        converted_files = data.get("converted_files", [])
        return converted_files if isinstance(converted_files, list) else []
    return []


def _save_manifest(manifest_path: Path, manifest: dict[str, object]) -> Path:
    ensure_dir(manifest_path.parent)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def convert_documents(input_dirs: list[Path], output_dir: Path, force: bool = False) -> list[Path]:
    ensure_dir(output_dir)
    manifest_path = output_dir / MANIFEST_NAME
    log_path = output_dir / ERROR_LOG_NAME

    converted_paths: list[Path] = []
    manifest_records: list[dict[str, str]] = []

    source_files: list[Path] = []
    for input_dir in input_dirs:
        if not input_dir.exists():
            continue
        for path in sorted(input_dir.rglob("*"), key=lambda p: p.name):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                source_files.append(path)

    seen: set[str] = set()
    unique_source_files: list[Path] = []
    for path in source_files:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_source_files.append(path)

    failed_records: list[dict[str, str]] = []

    for source_path in unique_source_files:
        file_type = source_path.suffix.lstrip(".").upper()
        output_path = output_dir / f"{source_path.name}.md"
        source_dir = str(source_path.parent.resolve())
        source_name = source_path.name

        if output_path.exists() and not force:
            status, method = _read_existing_metadata(output_path)
            if not status:
                status = "success"
            if not method:
                method = "existing"
            record = {
                "source_path": str(source_path.resolve()),
                "source_dir": source_dir,
                "output_path": str(output_path.resolve()),
                "file_type": file_type,
                "status": status,
                "method": method,
            }
            manifest_records.append(record)
            if status == "success":
                converted_paths.append(output_path)
            else:
                failed_records.append(record)
            continue

        if source_path.suffix.lower() == ".hwp":
            message = f"[docs] HWP 미지원: {source_name}\n[docs] Kordoc MCP 또는 수동 Markdown 변환이 필요합니다."
            print(message)
            _log_error(log_path, message)
            written = _write_conversion_output(
                output_path,
                source_name=source_name,
                file_type=file_type,
                method="failed",
                extracted_text="",
            )
            converted_paths.append(written)
            manifest_records.append(
                {
                    "source_path": str(source_path.resolve()),
                    "source_dir": source_dir,
                    "output_path": str(written.resolve()),
                    "file_type": file_type,
                    "status": "failed",
                    "method": "failed",
                }
            )
            failed_records.append(manifest_records[-1])
            continue

        kordoc_text = convert_hwpx_with_kordoc(source_path)
        if kordoc_text:
            written = _write_conversion_output(
                output_path,
                source_name=source_name,
                file_type=file_type,
                method="kordoc",
                extracted_text=kordoc_text,
            )
            converted_paths.append(written)
            manifest_records.append(
                {
                    "source_path": str(source_path.resolve()),
                    "source_dir": source_dir,
                    "output_path": str(written.resolve()),
                    "file_type": file_type,
                    "status": "success",
                    "method": "kordoc",
                }
            )
            continue

        fallback_text = _extract_hwpx_text_fallback(source_path)
        if fallback_text:
            written = _write_conversion_output(
                output_path,
                source_name=source_name,
                file_type=file_type,
                method="hwpx-xml-fallback",
                extracted_text=fallback_text,
            )
            converted_paths.append(written)
            manifest_records.append(
                {
                    "source_path": str(source_path.resolve()),
                    "source_dir": source_dir,
                    "output_path": str(written.resolve()),
                    "file_type": file_type,
                    "status": "success",
                    "method": "hwpx-xml-fallback",
                }
            )
            continue

        message = f"[docs] HWPX 변환 실패: {source_name}\n[docs] Kordoc MCP 또는 수동 Markdown 변환이 필요합니다."
        print(message)
        _log_error(log_path, message)
        written = _write_conversion_output(
            output_path,
            source_name=source_name,
            file_type=file_type,
            method="failed",
            extracted_text="",
        )
        converted_paths.append(written)
        manifest_records.append(
            {
                "source_path": str(source_path.resolve()),
                "source_dir": source_dir,
                "output_path": str(written.resolve()),
                "file_type": file_type,
                "status": "failed",
                "method": "failed",
            }
        )
        failed_records.append(manifest_records[-1])

    manifest = {
        "input_count": len(unique_source_files),
        "converted_count": len(manifest_records) - len(failed_records),
        "failed_count": len(failed_records),
        "converted_files": [record for record in manifest_records if record.get("status") == "success"],
        "failed_files": failed_records,
    }
    _save_manifest(manifest_path, manifest)
    return converted_paths


def load_converted_documents(source_dir: Path, output_dir: Path) -> list[Path]:
    manifest_path = output_dir / MANIFEST_NAME
    records = _load_manifest(manifest_path)
    source_dir_resolved = str(source_dir.resolve())
    paths: list[Path] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("status", "")).lower() != "success":
            continue
        if str(record.get("source_dir", "")) != source_dir_resolved:
            continue
        output_path_str = str(record.get("output_path", ""))
        if not output_path_str:
            continue
        output_path = Path(output_path_str)
        if output_path.exists():
            paths.append(output_path)

    return sorted(paths, key=lambda p: p.name)
