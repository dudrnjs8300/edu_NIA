from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.utils.file_utils import ensure_dir, write_utf8

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - handled at runtime
    WhisperModel = None


AUDIO_EXTENSIONS: set[str] = {".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac"}


FFMPEG_GUIDANCE = (
    "mp4/video 디코딩에 실패했습니다. ffmpeg 설치 또는 오디오 추출이 필요할 수 있습니다. "
    "ffmpeg가 PATH에 있는지 확인하고, 필요하면 mp4를 오디오 파일로 변환한 뒤 다시 실행하세요."
)


def _list_audio_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(
        [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS],
        key=lambda path: path.name,
    )


def _safe_table_cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\r", " ").replace("\n", " ").strip()


def _render_transcript_markdown(
    audio_name: str,
    model_size: str,
    language: str,
    full_text: str,
    segments: list[object],
) -> str:
    lines: list[str] = [
        "# 음성 녹취 변환 결과",
        "",
        f"- 원본 파일: {audio_name}",
        f"- STT 모델: faster-whisper {model_size}",
        f"- 언어: {language}",
        "",
        "## 전체 녹취문",
        "",
        full_text.strip() or "녹취문 없음",
        "",
        "## 구간별 녹취",
        "",
        "| 시작 | 종료 | 내용 |",
        "|---:|---:|---|",
    ]

    if segments:
        for segment in segments:
            start = f"{float(getattr(segment, 'start', 0.0)):.2f}"
            end = f"{float(getattr(segment, 'end', 0.0)):.2f}"
            text = _safe_table_cell(str(getattr(segment, "text", ""))) or "내용 없음"
            lines.append(f"| {start} | {end} | {text} |")
    else:
        lines.append("| 0.00 | 0.00 | 내용 없음 |")

    return "\n".join(lines).strip() + "\n"


def _load_transcript_source_name(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("- 원본 파일:"):
            return line.split(":", 1)[1].strip()
    return ""


def _append_error_log(error_log_path: Path, messages: list[str]) -> Path:
    if not messages:
        return error_log_path
    ensure_dir(error_log_path.parent)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with error_log_path.open("a", encoding="utf-8") as f:
        for message in messages:
            f.write(f"[{timestamp}] {message}\n")
    return error_log_path


def _normalize_language(language: str | None) -> str:
    normalized = (language or "").strip()
    return normalized or "auto"


def _format_transcription_error(audio_path: Path, exc: Exception) -> str:
    message = f"{audio_path.name}: {exc}"
    lowered = str(exc).lower()
    if audio_path.suffix.lower() == ".mp4" or any(token in lowered for token in ["ffmpeg", "av", "decoder", "decode", "invalid data"]):
        message = f"{message} | {FFMPEG_GUIDANCE}"
    return message


def transcribe_audio_files(
    input_dir: Path,
    output_dir: Path,
    model_size: str = "small",
    language: str | None = "auto",
    force: bool = False,
) -> dict[str, list[Path]]:
    audio_files = _list_audio_files(input_dir)
    transcripts_dir = ensure_dir(output_dir / "transcripts")
    language_setting = _normalize_language(language)

    if not audio_files:
        print("STT 대상 음성파일이 없습니다.")
        return {"transcripts": []}

    transcript_paths: list[Path] = []
    error_messages: list[str] = []

    pending_audio_files: list[Path] = []
    for audio_path in audio_files:
        transcript_md_path = transcripts_dir / f"{audio_path.stem}.transcript.md"
        transcript_txt_path = transcripts_dir / f"{audio_path.stem}.transcript.txt"
        if not force and transcript_md_path.exists() and transcript_txt_path.exists():
            transcript_paths.extend([transcript_md_path, transcript_txt_path])
            continue
        pending_audio_files.append(audio_path)

    if not pending_audio_files:
        return {"transcripts": transcript_paths}

    if WhisperModel is None:
        raise RuntimeError("faster-whisper가 설치되어 있지 않습니다. pip install faster-whisper 를 실행하세요.")

    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    for audio_path in pending_audio_files:
        transcript_md_path = transcripts_dir / f"{audio_path.stem}.transcript.md"
        transcript_txt_path = transcripts_dir / f"{audio_path.stem}.transcript.txt"

        try:
            segments, _info = model.transcribe(
                str(audio_path),
                vad_filter=True,
                **({} if language_setting == "auto" else {"language": language_setting}),
            )
            segment_list = list(segments)
            full_text = "\n".join(
                str(getattr(segment, "text", "")).strip() for segment in segment_list if str(getattr(segment, "text", "")).strip()
            ).strip()

            markdown_text = _render_transcript_markdown(
                audio_name=audio_path.name,
                model_size=model_size,
                language=language_setting,
                full_text=full_text,
                segments=segment_list,
            )
            text_output = full_text + ("\n" if full_text else "")

            write_utf8(transcript_md_path, markdown_text)
            write_utf8(transcript_txt_path, text_output)
            transcript_paths.extend([transcript_md_path, transcript_txt_path])
        except Exception as exc:  # pragma: no cover - runtime transcription errors
            error_message = _format_transcription_error(audio_path, exc)
            error_messages.append(error_message)
            print(error_message)

    if error_messages:
        error_log_path = _append_error_log(transcripts_dir / "stt_errors.log", error_messages)
        return {"transcripts": transcript_paths, "errors": [error_log_path]}

    return {"transcripts": transcript_paths}
