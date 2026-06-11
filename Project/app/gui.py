from __future__ import annotations

import io
import os
import queue
import shutil
import subprocess
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tkinter import BOTH, DISABLED, END, LEFT, NORMAL, RIGHT, X, Y, filedialog, messagebox, scrolledtext, Tk, StringVar, Text, Frame, Listbox, ttk

from app.pipeline import Edu2WorkPipeline
from app.utils.file_utils import ensure_workspace
from app.utils.json_utils import write_json

try:  # optional richer widgets
    import customtkinter as ctk
except ImportError:  # pragma: no cover - optional dependency
    ctk = None


EDU_EXTENSIONS = (".txt", ".md", ".hwpx", ".hwp", ".pptx", ".ppt", ".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac")
CSV_EXTENSIONS = (".csv",)

BG = "#F5F7FB"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#D8E1EE"
TEXT = "#0F172A"
MUTED = "#64748B"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#DBEAFE"
SUCCESS = "#0F766E"
ERROR = "#B91C1C"


class _TeeQueueWriter(io.TextIOBase):
    def __init__(self, log_queue: queue.Queue[str], mirror: io.TextIOBase | None = None) -> None:
        self._queue = log_queue
        self._mirror = mirror
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        if self._mirror is not None:
            self._mirror.write(text)
            self._mirror.flush()

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._queue.put(line + "\n")
        return len(text)

    def flush(self) -> None:
        if self._mirror is not None:
            self._mirror.flush()
        if self._buffer:
            self._queue.put(self._buffer)
            self._buffer = ""


class Edu2WorkGUI:
    def __init__(self) -> None:
        self.using_ctk = ctk is not None
        if self.using_ctk:
            ctk.set_appearance_mode("Light")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
            self.root.configure(fg_color=BG)
        else:
            self.root = Tk()
            self.root.configure(bg=BG)
            self._configure_ttk_style()

        self.root.title("Edu2WorkAI")
        self.root.geometry("960x700")
        self.root.minsize(900, 650)

        self.project_root = self._project_root()
        self.pipeline = Edu2WorkPipeline(project_root=self.project_root)
        self._ensure_runtime_config()
        ensure_workspace(self.pipeline.workspace_root)
        self.run_log_path = self.pipeline.workspace_root / "run_logs" / "latest_run.log"

        self.education_files: list[Path] = []
        self.ntis_csv: Path | None = None

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self.worker_failed = False
        self.worker_error_message = ""
        self.results_ready = self._results_exist()
        self.llm_test_running = False
        self.llm_test_failed = False
        self.llm_test_message = ""

        self.education_var = StringVar(value="선택된 교육자료 없음")
        self.education_preview_var = StringVar(value="아직 선택된 파일이 없습니다.")
        self.csv_var = StringVar(value="선택된 NTIS CSV 없음")
        self.status_var = StringVar(value="대기 중")
        self.llm_status_var = StringVar(value="LLM 상태를 불러오는 중입니다.")
        self.llm_detail_var = StringVar(value="")
        self.llm_key_var = StringVar(value="API Key 상태: 확인 전")
        self.llm_error_var = StringVar(value="마지막 LLM 오류: 없음")
        self.api_key_input_var = StringVar(value="")

        self._build_ui()
        self._refresh_result_buttons()
        self._poll_logs()

    def _configure_ttk_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD_BG, relief="solid", borderwidth=1)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=CARD_BG, foreground=TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("Body.TLabel", background=CARD_BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=CARD_BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10, "italic"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Compact.TButton", font=("Segoe UI", 9), padding=(10, 6))

    def _project_root(self) -> Path:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                return Path(meipass).resolve().parent
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[1]

    def _ensure_runtime_config(self) -> None:
        config_path = self.project_root / "config.json"
        if config_path.exists():
            pass
        else:
            write_json(
                config_path,
                {
                    "LLM": {
                        "enabled": True,
                        "provider": "openai_compatible",
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o-mini",
                        "api_key_env": "OPENAI_API_KEY",
                        "timeout": 60,
                        "temperature": 0.2,
                        "max_tokens": 1500,
                        "max_input_chars": 6000,
                        "use_for_education_summary": True,
                        "use_for_idea_cards": False,
                        "use_for_ai_diagnosis": True,
                    }
                },
            )

        readme_path = self.project_root / "README.md"
        if not readme_path.exists():
            bundled_readme = Path(__file__).resolve().parents[1] / "README.md"
            if bundled_readme.exists():
                readme_path.write_text(bundled_readme.read_text(encoding="utf-8"), encoding="utf-8")

    def _frame(self, parent: Frame | object, *, card: bool = False):
        if self.using_ctk:
            return ctk.CTkFrame(
                parent,
                fg_color=CARD_BG if card else BG,
                corner_radius=18 if card else 0,
                border_width=1 if card else 0,
                border_color=CARD_BORDER if card else BG,
            )
        return ttk.Frame(parent, style="Card.TFrame" if card else "App.TFrame")

    def _label(self, parent: Frame | object, *, text: str = "", kind: str = "body", anchor: str = "w", wraplength: int | None = None):
        if self.using_ctk:
            font_map = {
                "title": ("Segoe UI", 20, "bold"),
                "subtitle": ("Segoe UI", 11),
                "section": ("Segoe UI", 12, "bold"),
                "status": ("Segoe UI", 10, "italic"),
                "body": ("Segoe UI", 10),
                "muted": ("Segoe UI", 9),
            }
            color_map = {
                "title": TEXT,
                "subtitle": MUTED,
                "section": TEXT,
                "status": MUTED,
                "body": TEXT,
                "muted": MUTED,
            }
            return ctk.CTkLabel(parent, text=text, text_color=color_map.get(kind, TEXT), font=font_map.get(kind, ("Segoe UI", 10)), justify="left", anchor=anchor)
        style_map = {
            "title": "Title.TLabel",
            "subtitle": "Subtitle.TLabel",
            "section": "Section.TLabel",
            "status": "Status.TLabel",
            "body": "Body.TLabel",
            "muted": "Muted.TLabel",
        }
        return ttk.Label(parent, text=text, style=style_map.get(kind, "Body.TLabel"), anchor=anchor, wraplength=wraplength)

    def _button(self, parent: Frame | object, *, text: str, command, primary: bool = False, compact: bool = False, width: int | None = None):
        if self.using_ctk:
            button_kwargs = {
                "text": text,
                "command": command,
                "height": 40 if primary else 34,
                "corner_radius": 12,
                "fg_color": ACCENT if primary else "#E5EDF8",
                "hover_color": ACCENT_HOVER if primary else "#D7E3F5",
                "text_color": "#FFFFFF" if primary else TEXT,
                "font": ("Segoe UI", 11, "bold" if primary else "normal") if not compact else ("Segoe UI", 10),
            }
            if width is not None:
                button_kwargs["width"] = width
            return ctk.CTkButton(parent, **button_kwargs)
        style = "Primary.TButton" if primary else ("Compact.TButton" if compact else "Secondary.TButton")
        return ttk.Button(parent, text=text, command=command, style=style)

    def _entry(self, parent: Frame | object, *, textvariable: StringVar, show: str = ""):
        if self.using_ctk:
            return ctk.CTkEntry(parent, textvariable=textvariable, show=show, height=34)
        return ttk.Entry(parent, textvariable=textvariable, show=show)

    def _text_widget(self, parent: Frame | object, *, height: int, monospace: bool = False):
        font = ("Consolas", 10) if monospace else ("Segoe UI", 10)
        widget = scrolledtext.ScrolledText(parent, wrap="word", height=height, font=font, bg="#FFFFFF", fg=TEXT, insertbackground=TEXT, relief="solid", borderwidth=1)
        widget.configure(state=DISABLED)
        return widget

    def _build_ui(self) -> None:
        main = self._frame(self.root)
        main.pack(fill=BOTH, expand=True, padx=20, pady=20)

        self._build_hero(main)
        self._build_input_cards(main)
        self._build_llm_card(main)
        self._build_actions_card(main)
        self._build_log_card(main)
        self._build_status_row(main)

    def _build_hero(self, parent) -> None:
        frame = self._frame(parent, card=True)
        frame.pack(fill=X, pady=(0, 14))
        if self.using_ctk:
            frame.grid_columnconfigure(0, weight=1)
        else:
            frame.columnconfigure(0, weight=1)

        title = self._label(frame, text="Edu2WorkAI", kind="title")
        subtitle = self._label(frame, text="AI 교육자료와 부서 업무자료를 연결해 활용 아이디어와 보고서를 생성합니다.", kind="subtitle")
        title.pack(anchor="w", padx=18, pady=(16, 4))
        subtitle.pack(anchor="w", padx=18, pady=(0, 16))

        status_bar = self._frame(frame)
        status_bar.pack(fill=X, padx=18, pady=(0, 16))
        self.status_badge = self._label(status_bar, text=self.status_var.get(), kind="status") if hasattr(self, "status_var") else None
        if self.status_badge is not None:
            self.status_badge.pack(anchor="w")

    def _build_input_cards(self, parent) -> None:
        container = self._frame(parent)
        container.pack(fill=X, pady=(0, 14))
        if not self.using_ctk:
            container.columnconfigure(0, weight=1)
            container.columnconfigure(1, weight=1)

        left = self._frame(container, card=True)
        right = self._frame(container, card=True)
        if self.using_ctk:
            left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
            right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))
        else:
            left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_education_card(left)
        self._build_csv_card(right)

    def _build_education_card(self, parent) -> None:
        self._label(parent, text="교육자료 선택", kind="section").pack(anchor="w", padx=16, pady=(16, 6))
        self._label(parent, text="지원: txt, md, pptx, ppt, mp3, wav, m4a, mp4, aac, flac, hwpx, hwp", kind="muted", wraplength=390).pack(anchor="w", padx=16)

        button_row = self._frame(parent)
        button_row.pack(fill=X, padx=16, pady=(12, 8))
        self.education_button = self._button(button_row, text="교육자료 선택", command=self.choose_education_files, primary=False)
        self.education_button.pack(side=LEFT)
        self.clear_education_button = self._button(button_row, text="선택 해제", command=self.clear_education_files, compact=True)
        self.clear_education_button.pack(side=LEFT, padx=8)

        self.education_summary_label = self._label(parent, text=self.education_var.get(), kind="body")
        self.education_summary_label.pack(anchor="w", padx=16, pady=(4, 4))

        self.education_preview = Text(parent, height=5, wrap="word", font=("Consolas", 10), bg="#F8FAFC", fg=TEXT, relief="solid", borderwidth=1)
        self.education_preview.pack(fill=X, padx=16, pady=(0, 16))
        self.education_preview.insert("1.0", self.education_preview_var.get())
        self.education_preview.configure(state=DISABLED)

    def _build_csv_card(self, parent) -> None:
        self._label(parent, text="NTIS CSV 선택", kind="section").pack(anchor="w", padx=16, pady=(16, 6))
        self._label(parent, text="지원: csv", kind="muted").pack(anchor="w", padx=16)

        button_row = self._frame(parent)
        button_row.pack(fill=X, padx=16, pady=(12, 8))
        self.csv_button = self._button(button_row, text="NTIS CSV 선택", command=self.choose_ntis_csv)
        self.csv_button.pack(side=LEFT)
        self.clear_csv_button = self._button(button_row, text="선택 해제", command=self.clear_ntis_csv, compact=True)
        self.clear_csv_button.pack(side=LEFT, padx=8)

        self.csv_label = self._label(parent, text=self.csv_var.get(), kind="body")
        self.csv_label.pack(anchor="w", padx=16, pady=(4, 16))

    def _build_llm_card(self, parent) -> None:
        frame = self._frame(parent, card=True)
        frame.pack(fill=X, pady=(0, 14))

        self._label(frame, text="LLM 상태", kind="section").pack(anchor="w", padx=16, pady=(16, 6))
        self.llm_status_label = self._label(frame, text=self.llm_status_var.get(), kind="body")
        self.llm_status_label.pack(anchor="w", padx=16)
        self.llm_detail_label = self._label(frame, text=self.llm_detail_var.get(), kind="muted", wraplength=900)
        self.llm_detail_label.pack(anchor="w", padx=16, pady=(2, 0))
        self.llm_key_label = self._label(frame, text=self.llm_key_var.get(), kind="muted")
        self.llm_key_label.pack(anchor="w", padx=16, pady=(2, 0))
        self.llm_error_label = self._label(frame, text=self.llm_error_var.get(), kind="muted", wraplength=900)
        self.llm_error_label.pack(anchor="w", padx=16, pady=(2, 0))

        input_row = self._frame(frame)
        input_row.pack(fill=X, padx=16, pady=(12, 8))
        self.api_key_entry = self._entry(input_row, textvariable=self.api_key_input_var, show="*")
        if self.using_ctk:
            self.api_key_entry.pack(side=LEFT, fill=X, expand=True)
        else:
            self.api_key_entry.pack(side=LEFT, fill=X, expand=True)

        button_row = self._frame(frame)
        button_row.pack(fill=X, padx=16, pady=(0, 16))
        self.apply_api_key_button = self._button(button_row, text="현재 세션에 적용", command=self.apply_api_key, compact=True)
        self.apply_api_key_button.pack(side=LEFT)
        self.check_api_key_button = self._button(button_row, text="API Key 확인", command=self.refresh_llm_status, compact=True)
        self.check_api_key_button.pack(side=LEFT, padx=8)
        self.test_llm_button = self._button(button_row, text="LLM 테스트", command=self.test_llm, compact=True)
        self.test_llm_button.pack(side=LEFT, padx=8)

        self.refresh_llm_status()

    def _build_actions_card(self, parent) -> None:
        frame = self._frame(parent, card=True)
        frame.pack(fill=X, pady=(0, 14))

        self._label(frame, text="실행", kind="section").pack(anchor="w", padx=16, pady=(16, 6))
        self._label(frame, text="입력 파일을 workspace에 복사한 뒤 전체 파이프라인을 실행합니다.", kind="muted").pack(anchor="w", padx=16)

        action_row = self._frame(frame)
        action_row.pack(fill=X, padx=16, pady=(14, 8))
        self.run_button = self._button(action_row, text="분석 실행", command=self.run_analysis, primary=True, width=180)
        self.run_button.pack(side=LEFT)
        self.run_status_label = self._label(action_row, text=self.status_var.get(), kind="status")
        self.run_status_label.pack(side=LEFT, padx=14)

        results_row = self._frame(frame)
        results_row.pack(fill=X, padx=16, pady=(0, 16))
        self.open_button = self._button(results_row, text="결과 폴더 열기", command=self.open_results_folder)
        self.open_button.pack(side=LEFT)
        self.open_education_report_button = self._button(results_row, text="교육결과 보고서", command=self.open_education_result_report, compact=True)
        self.open_education_report_button.pack(side=LEFT, padx=8)
        self.open_ai_report_button = self._button(results_row, text="AI 진단 보고서", command=self.open_ai_diagnosis_report, compact=True)
        self.open_ai_report_button.pack(side=LEFT, padx=8)
        self.open_ideas_button = self._button(results_row, text="아이디어 카드", command=self.open_idea_cards, compact=True)
        self.open_ideas_button.pack(side=LEFT, padx=8)

    def _build_log_card(self, parent) -> None:
        frame = self._frame(parent, card=True)
        frame.pack(fill=BOTH, expand=True, pady=(0, 12))

        self._label(frame, text="실행 로그", kind="section").pack(anchor="w", padx=16, pady=(16, 6))
        self._label(frame, text="분석 실행 중 출력되는 메시지가 순서대로 표시됩니다.", kind="muted").pack(anchor="w", padx=16, pady=(0, 8))

        self.log_text = self._text_widget(frame, height=16, monospace=True)
        self.log_text.pack(fill=BOTH, expand=True, padx=16, pady=(0, 16))

    def _build_status_row(self, parent) -> None:
        row = self._frame(parent)
        row.pack(fill=X)
        self.footer_status_label = self._label(row, text=self.status_var.get(), kind="status")
        self.footer_status_label.pack(anchor="w")

    def _results_exist(self) -> bool:
        return all(
            path.exists()
            for path in [
                self.pipeline.workspace_root / "07_final_report" / "education_result_report.md",
                self.pipeline.workspace_root / "07_final_report" / "AI_diagnosis_report.md",
                self.pipeline.workspace_root / "06_matching_output" / "idea_cards.md",
            ]
        )

    def _set_running(self, running: bool) -> None:
        self.running = running
        state = DISABLED if running else NORMAL
        self.run_button.configure(state=state)
        self.education_button.configure(state=state)
        self.csv_button.configure(state=state)
        self.clear_education_button.configure(state=state)
        self.clear_csv_button.configure(state=state)
        if hasattr(self, "apply_api_key_button"):
            self.apply_api_key_button.configure(state=state)
        if hasattr(self, "check_api_key_button"):
            self.check_api_key_button.configure(state=state)
        if hasattr(self, "test_llm_button"):
            self.test_llm_button.configure(state=state)
        self.status_var.set("분석 중입니다..." if running else ("대기 중" if not self.results_ready else "분석이 완료되었습니다."))
        self.run_status_label.configure(text=self.status_var.get())
        if hasattr(self, "footer_status_label"):
            try:
                self.footer_status_label.configure(text=self.status_var.get())
            except Exception:
                pass

    def _refresh_result_buttons(self) -> None:
        enabled = NORMAL if self.results_ready else DISABLED
        self.open_button.configure(state=enabled)
        self.open_education_report_button.configure(state=enabled)
        self.open_ai_report_button.configure(state=enabled)
        self.open_ideas_button.configure(state=enabled)

    def _clear_workspace_inputs(self) -> None:
        staged_dirs = [
            self.pipeline.workspace_root / "01_education_raw",
            self.pipeline.workspace_root / "03_ntis_raw",
            self.pipeline.workspace_root / "02_education_processed" / "transcripts",
            self.pipeline.workspace_root / "02_education_processed" / "ppt_extracts",
        ]
        for directory in staged_dirs:
            directory.mkdir(parents=True, exist_ok=True)
            for path in directory.iterdir():
                if path.is_file():
                    path.unlink()

    def _copy_selected_files(self) -> None:
        self._clear_workspace_inputs()

        if self.education_files:
            dest_dir = self.pipeline.workspace_root / "01_education_raw"
            dest_dir.mkdir(parents=True, exist_ok=True)
            for source in self.education_files:
                shutil.copy2(source, dest_dir / source.name)

        if self.ntis_csv is not None:
            dest_dir = self.pipeline.workspace_root / "03_ntis_raw"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.ntis_csv, dest_dir / self.ntis_csv.name)

    def _selection_preview_lines(self, paths: list[Path]) -> list[str]:
        if not paths:
            return ["아직 선택된 파일이 없습니다."]
        preview = [p.name for p in paths[:5]]
        extra = len(paths) - len(preview)
        if extra > 0:
            preview.append(f"외 {extra}개")
        return preview

    def _update_education_display(self) -> None:
        if not self.education_files:
            self.education_var.set("선택된 교육자료 없음")
            preview_lines = ["아직 선택된 파일이 없습니다."]
        else:
            self.education_var.set(f"선택된 교육자료: {len(self.education_files)}개")
            preview_lines = self._selection_preview_lines(self.education_files)
        self.education_summary_label.configure(text=self.education_var.get())
        self.education_preview.configure(state=NORMAL)
        self.education_preview.delete("1.0", END)
        self.education_preview.insert("1.0", "\n".join(preview_lines))
        self.education_preview.configure(state=DISABLED)

    def _update_csv_display(self) -> None:
        if self.ntis_csv is None:
            self.csv_var.set("선택된 NTIS CSV 없음")
        else:
            self.csv_var.set(f"선택된 NTIS CSV: {self.ntis_csv.name}")
        self.csv_label.configure(text=self.csv_var.get())

    def _set_label_text(self, label, text: str) -> None:
        try:
            label.configure(text=text)
        except Exception:
            pass

    def refresh_llm_status(self) -> None:
        client = self.pipeline._llm_client()
        snapshot = client.status_snapshot()
        mode = str(snapshot.get("current_mode", "disabled"))
        enabled = bool(snapshot.get("enabled", False))
        provider = str(snapshot.get("provider", ""))
        model = str(snapshot.get("model", ""))
        api_key_env = str(snapshot.get("api_key_env", ""))
        api_key_found = bool(snapshot.get("api_key_found", False))
        last_error = str(snapshot.get("last_error_message", "")).strip() or "없음"

        self.llm_status_var.set(f"현재 모드: {mode}")
        self.llm_detail_var.set(f"enabled={str(enabled).lower()} | provider={provider} | model={model} | api_key_env={api_key_env}")
        self.llm_key_var.set(f"API Key 상태: {'있음' if api_key_found else '없음'}")
        self.llm_error_var.set(f"마지막 LLM 오류: {last_error}")

        if hasattr(self, "llm_status_label"):
            self._set_label_text(self.llm_status_label, self.llm_status_var.get())
        if hasattr(self, "llm_detail_label"):
            self._set_label_text(self.llm_detail_label, self.llm_detail_var.get())
        if hasattr(self, "llm_key_label"):
            self._set_label_text(self.llm_key_label, self.llm_key_var.get())
        if hasattr(self, "llm_error_label"):
            self._set_label_text(self.llm_error_label, self.llm_error_var.get())

    def apply_api_key(self) -> None:
        api_key = self.api_key_input_var.get().strip()
        if not api_key:
            messagebox.showwarning("안내", "API Key를 입력하세요.")
            return
        os.environ["OPENAI_API_KEY"] = api_key
        client = self.pipeline._llm_client()
        client.disabled_for_session = False
        client.last_error_kind = ""
        client.last_error_message = ""
        self.refresh_llm_status()
        messagebox.showinfo("적용 완료", "현재 세션에 API Key를 적용했습니다. 파일에는 저장하지 않습니다.")

    def test_llm(self) -> None:
        if self.llm_test_running:
            return
        self.llm_test_running = True
        if hasattr(self, "test_llm_button"):
            self.test_llm_button.configure(state=DISABLED)
        self._append_log("[llm-test] 테스트를 시작합니다.\n")

        def worker() -> None:
            try:
                ok, detail = self.pipeline._llm_client().test_connection()
                if ok:
                    self.llm_test_failed = False
                    self.llm_test_message = detail
                    self.log_queue.put("[llm-test] success\n")
                else:
                    self.llm_test_failed = True
                    self.llm_test_message = detail
                    self.log_queue.put(f"[llm-test] failed: {detail}\n")
            except Exception as exc:
                self.llm_test_failed = True
                self.llm_test_message = str(exc)
                self.log_queue.put(f"[llm-test] failed: {exc}\n")
                self.log_queue.put(traceback.format_exc())
            finally:
                self.log_queue.put("__LLMTEST_DONE__")

        threading.Thread(target=worker, daemon=True).start()

    def clear_education_files(self) -> None:
        self.education_files = []
        self._update_education_display()

    def clear_ntis_csv(self) -> None:
        self.ntis_csv = None
        self._update_csv_display()

    def choose_education_files(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="교육자료 선택",
            initialdir=str(self.project_root),
            filetypes=[("교육자료", "*.txt *.md *.hwpx *.hwp *.pptx *.ppt *.mp3 *.wav *.m4a *.mp4 *.aac *.flac"), ("모든 파일", "*.*")],
        )
        if not file_paths:
            return

        selected = [Path(path) for path in file_paths]
        self.education_files = [path for path in selected if path.suffix.lower() in EDU_EXTENSIONS]
        self._update_education_display()

    def choose_ntis_csv(self) -> None:
        file_path = filedialog.askopenfilename(
            title="NTIS CSV 선택",
            initialdir=str(self.project_root),
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )
        if not file_path:
            return

        selected = Path(file_path)
        if selected.suffix.lower() not in CSV_EXTENSIONS:
            messagebox.showwarning("안내", "CSV 파일만 선택할 수 있습니다.")
            return
        self.ntis_csv = selected
        self._update_csv_display()

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=NORMAL)
        self.log_text.insert(END, text)
        self.log_text.see(END)
        self.log_text.configure(state=DISABLED)
        try:
            self.run_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.run_log_path.open("a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def _reset_run_log(self) -> None:
        try:
            self.run_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.run_log_path.write_text("", encoding="utf-8")
        except Exception:
            pass

    def run_analysis(self) -> None:
        if not self.education_files and self.ntis_csv is None:
            messagebox.showwarning("안내", "교육자료 또는 NTIS CSV 중 하나 이상을 선택하세요.")
            return

        if self.running:
            return

        self._set_running(True)
        self.worker_failed = False
        self.worker_error_message = ""
        self.results_ready = False
        self._reset_run_log()
        self.refresh_llm_status()
        self._refresh_result_buttons()
        self._append_log("[gui] 파일 복사 및 파이프라인 실행을 시작합니다.\n")
        for line in self.pipeline._llm_client().status_lines():
            self._append_log(line + "\n")

        worker = threading.Thread(target=self._run_pipeline_worker, daemon=True)
        worker.start()

    def _run_pipeline_worker(self) -> None:
        try:
            self._copy_selected_files()
            tee_stream = _TeeQueueWriter(self.log_queue, mirror=getattr(sys, "__stdout__", None))
            with redirect_stdout(tee_stream), redirect_stderr(tee_stream):
                self.pipeline.run_all()
            self.log_queue.put("__SUCCESS__")
        except Exception as exc:
            self.worker_failed = True
            self.worker_error_message = f"{type(exc).__name__}: {exc}"
            self.log_queue.put(f"__ERROR__:{self.worker_error_message}")
            self.log_queue.put(traceback.format_exc())
        finally:
            self.log_queue.put("__DONE__")

    def _poll_logs(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item == "__SUCCESS__":
                    continue
                if item == "__LLMTEST_DONE__":
                    self.llm_test_running = False
                    if hasattr(self, "test_llm_button"):
                        self.test_llm_button.configure(state=NORMAL if not self.running else DISABLED)
                    self.refresh_llm_status()
                    if self.llm_test_failed:
                        messagebox.showerror("LLM 테스트 실패", f"LLM 테스트 실패: {self.llm_test_message}")
                    else:
                        messagebox.showinfo("LLM 테스트 성공", "LLM 테스트 성공")
                    continue
                if item == "__DONE__":
                    self._set_running(False)
                    self.results_ready = not self.worker_failed and self._results_exist()
                    self._refresh_result_buttons()
                    if self.worker_failed:
                        error_text = self.worker_error_message or "로그를 확인하세요."
                        self.status_var.set(f"분석 중 오류가 발생했습니다: {error_text}")
                        self.run_status_label.configure(text=self.status_var.get())
                        if hasattr(self, "footer_status_label"):
                            self.footer_status_label.configure(text=self.status_var.get())
                        messagebox.showerror("오류", self.status_var.get())
                    else:
                        self.status_var.set("분석이 완료되었습니다.")
                        self.run_status_label.configure(text=self.status_var.get())
                        if hasattr(self, "footer_status_label"):
                            self.footer_status_label.configure(text=self.status_var.get())
                        messagebox.showinfo("완료", "분석이 완료되었습니다.")
                    continue
                if item.startswith("__ERROR__:"):
                    error_text = item.split(":", 1)[1].strip()
                    self._set_running(False)
                    self.results_ready = self._results_exist()
                    self._refresh_result_buttons()
                    self.status_var.set(f"분석 중 오류가 발생했습니다: {error_text}")
                    self.run_status_label.configure(text=self.status_var.get())
                    if hasattr(self, "footer_status_label"):
                        self.footer_status_label.configure(text=self.status_var.get())
                    self._append_log(f"[error] 분석 중 오류가 발생했습니다: {error_text}\n")
                    continue
                self._append_log(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_logs)

    def _open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showwarning("안내", f"파일을 찾을 수 없습니다.\n{path}")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("오류", f"열 수 없습니다.\n{exc}")

    def open_results_folder(self) -> None:
        results_dir = self.pipeline.workspace_root / "07_final_report"
        results_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(results_dir)

    def open_education_result_report(self) -> None:
        self._open_path(self.pipeline.workspace_root / "07_final_report" / "education_result_report.md")

    def open_ai_diagnosis_report(self) -> None:
        self._open_path(self.pipeline.workspace_root / "07_final_report" / "AI_diagnosis_report.md")

    def open_idea_cards(self) -> None:
        self._open_path(self.pipeline.workspace_root / "06_matching_output" / "idea_cards.md")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    app = Edu2WorkGUI()
    app.run()


if __name__ == "__main__":
    main()
