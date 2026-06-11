from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.modules.department_mapper import build_department_map
from app.modules.document_converter import convert_documents
from app.modules.education_processor import process_education
from app.modules.exporter import export_final_packet
from app.modules.idea_generator import generate_idea_cards
from app.llm_client import LLMClient
from app.modules.ppt_processor import extract_ppt_files
from app.modules.stt_processor import transcribe_audio_files
from app.modules.report_parser import process_reports
from app.utils.file_utils import ensure_dir, ensure_workspace, write_utf8
from app.utils.json_utils import read_json, write_json
from app.utils.logging_utils import setup_logger


PROMPT_DEFAULTS: dict[str, str] = {
    "clean_education_text.md": "# clean_education_text\n\n교육 텍스트의 노이즈를 줄이고 분석 가능한 형태로 정리한다.",
    "extract_education_concepts.md": "# extract_education_concepts\n\n교육자료에서 핵심 주제와 실무 적용 방법을 구조화한다.",
    "summarize_research_report.md": "# summarize_research_report\n\n연구보고서를 섹션 단위로 요약해 업무 관점 정보를 추출한다.",
    "build_department_map.md": "# build_department_map\n\n보고서 요약을 연도별·업무영역별로 통합한다.",
    "generate_idea_cards.md": "# generate_idea_cards\n\n교육 주제와 업무 패턴을 연결한 아이디어 카드를 생성한다.",
    "write_final_report.md": "# write_final_report\n\n중간 산출물을 취합해 최종 보고서 초안을 작성한다.",
    "education_summary_system.txt": "교육자료 요약을 한국어 Markdown으로 작성하는 시스템 프롬프트입니다. 반드시 다음 구조를 유지하세요: # 교육자료 요약, ## 핵심 주제, ## 주요 내용, ## 업무 적용 가능성, ## 교육에서 얻은 시사점, ## LLM 사용 여부. 불필요한 설명은 줄이고, 교육자료의 핵심을 자연스럽게 정리하세요.",
    "idea_cards_system.txt": "교육내용과 업무자료를 연결해 아이디어 카드 설명을 보강하는 시스템 프롬프트입니다. 이미 있는 카드 구조를 유지하면서, 각 카드의 문제·기대효과·도입 포인트를 더 구체적이고 실무적으로 설명하세요. 한국어 Markdown으로 답하세요.",
    "ai_diagnosis_system.txt": "AI 활용 진단 보고서를 한국어 Markdown으로 다듬는 시스템 프롬프트입니다. 반드시 기존 섹션 구조를 유지하면서 문장을 자연스럽고 보고서답게 정리하세요. 과장하지 말고, 실무 적용 관점의 표현을 사용하세요.",
}


CONFIG_DEFAULT: dict[str, object] = {
    "STT": {"enabled": True, "model_size": "small", "language": "auto"},
    "LLM": {
        "enabled": False,
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
    },
}


SCHEMA_DEFAULTS: dict[str, str] = {
    "education_concepts.schema.json": """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EducationConcepts",
  "type": "object",
  "properties": {
    "concepts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "description": {"type": "string"},
          "source": {"type": "string"}
        },
        "required": ["name"]
      }
    }
  },
  "required": ["concepts"]
}
""",
    "report_summary.schema.json": """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ReportSummary",
  "type": "object",
  "properties": {
    "report_id": {"type": "string"},
    "summary": {"type": "string"}
  },
  "required": ["report_id", "summary"]
}
""",
    "department_work_map.schema.json": """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DepartmentWorkMap",
  "type": "object"
}
""",
    "idea_card.schema.json": """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "IdeaCard",
  "type": "object",
  "properties": {
    "id": {"type": "string"},
    "title": {"type": "string"}
  },
  "required": ["id", "title"]
}
""",
}


class Edu2WorkPipeline:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.workspace_root = self.project_root / "workspace"
        self.app_root = self.project_root / "app"
        self.prompts_root = self.app_root / "prompts"
        self.schemas_root = self.app_root / "schemas"
        self.config_path = self.project_root / "config.json"
        self._llm_client_instance: LLMClient | None = None

        self.logger = setup_logger()

    def _load_config(self) -> dict[str, object]:
        if not self.config_path.exists():
            return {}
        try:
            data = read_json(self.config_path)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _load_doc_manifest(self) -> dict[str, object]:
        manifest_path = self.workspace_root / "02_education_processed" / "doc_extracts" / "doc_extracts_manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            data = read_json(manifest_path)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _llm_client(self) -> LLMClient:
        if self._llm_client_instance is None:
            self._llm_client_instance = LLMClient(self._load_config())
        return self._llm_client_instance

    def _stt_settings(self) -> dict[str, object]:
        config = self._load_config()
        stt = config.get("STT", {}) if isinstance(config, dict) else {}
        if not isinstance(stt, dict):
            stt = {}
        raw_language = stt.get("language", "auto")
        language = "auto" if raw_language in (None, "") else str(raw_language).strip() or "auto"
        return {
            "enabled": bool(stt.get("enabled", True)),
            "model_size": str(stt.get("model_size", "small") or "small"),
            "language": language,
        }

    def _print_paths(self, paths: dict[str, object]) -> None:
        for key, path in paths.items():
            if isinstance(path, list):
                print(f"[{key}]")
                for item in path:
                    print(f"- {item}")
            else:
                print(f"[{key}] {path}")

    def _run_step(self, index: int, total: int, name: str, action: Callable[[], None], *, announce: bool = True) -> None:
        if announce:
            print(f"[run-all] {index}/{total} {name}", flush=True)
        try:
            action()
        except Exception as exc:
            print(f"[error] run-all failed at step: {name}", flush=True)
            print(f"원인: {exc}", flush=True)
            raise

    def _print_run_all_results(self) -> None:
        print("[done] 주요 결과 파일", flush=True)
        for path in [
            self.workspace_root / "02_education_processed" / "education_summary.md",
            self.workspace_root / "02_education_processed" / "education_concepts.json",
            self.workspace_root / "05_department_analysis" / "department_work_map.json",
            self.workspace_root / "05_department_analysis" / "department_timeline.md",
            self.workspace_root / "06_matching_output" / "idea_cards.md",
            self.workspace_root / "07_final_report" / "education_result_report.md",
            self.workspace_root / "07_final_report" / "AI_diagnosis_report.md",
            self.workspace_root / "07_final_report" / "final_report_draft.md",
        ]:
            print(path, flush=True)

    def init(self) -> None:
        created_dirs = ensure_workspace(self.workspace_root)
        ensure_dir(self.prompts_root)
        ensure_dir(self.schemas_root)

        if not self.config_path.exists():
            write_json(self.config_path, CONFIG_DEFAULT)

        for p in created_dirs:
            print(f"[workspace] {p}")

        created_files: dict[str, Path] = {}
        for name, content in PROMPT_DEFAULTS.items():
            path = self.prompts_root / name
            if not path.exists():
                created_files[name] = write_utf8(path, content)

        for name, content in SCHEMA_DEFAULTS.items():
            path = self.schemas_root / name
            if not path.exists():
                created_files[name] = write_utf8(path, content)

        self._print_paths(created_files)

    def process_education(self) -> None:
        stt_settings = self._stt_settings()
        llm_client = self._llm_client()
        if stt_settings["enabled"]:
            try:
                transcribe_audio_files(
                    input_dir=self.workspace_root / "01_education_raw",
                    output_dir=self.workspace_root / "02_education_processed",
                    model_size=str(stt_settings["model_size"]),
                    language=str(stt_settings["language"]),
                    force=False,
                )
            except RuntimeError as exc:
                print(str(exc))

        result = process_education(
            input_dir=self.workspace_root / "01_education_raw",
            output_dir=self.workspace_root / "02_education_processed",
            llm_client=llm_client,
        )
        self._print_paths(result)

    def convert_docs(self) -> None:
        result = convert_documents(
            input_dirs=[self.workspace_root / "01_education_raw", self.workspace_root / "04_ntis_md"],
            output_dir=self.workspace_root / "02_education_processed" / "doc_extracts",
            force=False,
        )
        manifest = self._load_doc_manifest()
        input_count = int(manifest.get("input_count", 0) or 0)
        converted_count = int(manifest.get("converted_count", 0) or 0)
        if input_count == 0:
            print("[converted_docs] 변환 대상 HWPX/HWP 파일이 없습니다.")
            return
        if converted_count == 0:
            print("[converted_docs] 변환된 문서가 없습니다. doc_errors.log를 확인하세요.")
            return

        print("[converted_docs]")
        for path in result:
            print(path)

    def transcribe_audio(self) -> None:
        stt_settings = self._stt_settings()
        if not stt_settings["enabled"]:
            print("STT가 비활성화되어 있습니다.")
            return

        try:
            result = transcribe_audio_files(
                input_dir=self.workspace_root / "01_education_raw",
                output_dir=self.workspace_root / "02_education_processed",
                model_size=str(stt_settings["model_size"]),
                language=str(stt_settings["language"]),
                force=False,
            )
        except RuntimeError as exc:
            print(str(exc))
            return

        self._print_paths(result)

    def extract_ppt(self) -> None:
        try:
            result = extract_ppt_files(
                input_dir=self.workspace_root / "01_education_raw",
                output_dir=self.workspace_root / "02_education_processed",
                force=False,
            )
        except RuntimeError as exc:
            print(str(exc))
            return

        self._print_paths(result)

    def process_reports(self) -> None:
        result = process_reports(
            input_dir=self.workspace_root / "04_ntis_md",
            output_jsonl_path=self.workspace_root / "05_department_analysis" / "report_summaries.jsonl",
        )
        self._print_paths(result)

    def build_map(self) -> None:
        result = build_department_map(
            report_summaries_jsonl=self.workspace_root / "05_department_analysis" / "report_summaries.jsonl",
            output_dir=self.workspace_root / "05_department_analysis",
        )
        self._print_paths(result)

    def generate_ideas(self) -> None:
        result = generate_idea_cards(
            education_concepts_path=self.workspace_root / "02_education_processed" / "education_concepts.json",
            department_map_path=self.workspace_root / "05_department_analysis" / "department_work_map.json",
            output_dir=self.workspace_root / "06_matching_output",
        )
        self._print_paths(result)

    def export(self) -> None:
        llm_client = self._llm_client()
        result = export_final_packet(
            workspace_root=self.workspace_root,
            output_dir=self.workspace_root / "07_final_report",
            llm_client=llm_client,
        )
        self._print_paths(result)

    def run_all(self) -> None:
        steps = [
            ("init", self.init),
            ("transcribe-audio", self.transcribe_audio),
            ("extract-ppt", self.extract_ppt),
            ("convert-docs", self.convert_docs),
            ("process-education", self.process_education),
            ("process-reports", self.process_reports),
            ("build-map", self.build_map),
            ("generate-ideas", self.generate_ideas),
            ("export", self.export),
        ]

        total = len(steps)
        for line in self._llm_client().status_lines():
            print(line, flush=True)
        try:
            for index, (name, action) in enumerate(steps, start=1):
                if name == "generate-ideas":
                    print(f"[run-all] {index}/{total} {name}", flush=True)
                    self._run_step(index, total, name, action, announce=False)
                else:
                    self._run_step(index, total, name, action)
        except Exception:
            return

        self._print_run_all_results()
