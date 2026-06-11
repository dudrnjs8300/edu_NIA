from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from dataclasses import field


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    timeout: int = 60
    temperature: float = 0.2
    max_tokens: int = 1500
    max_input_chars: int = 6000
    use_for_education_summary: bool = True
    use_for_idea_cards: bool = False
    use_for_ai_diagnosis: bool = True


@dataclass(frozen=True)
class AppConfig:
    provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:12b"
    temperature: float = 0.2
    max_input_chars: int = 12000
    llm: LLMConfig = field(default_factory=LLMConfig)


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        return AppConfig()

    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    llm_raw = raw.get("LLM", {}) if isinstance(raw, dict) else {}
    if not isinstance(llm_raw, dict):
        llm_raw = {}

    return AppConfig(
        provider=raw.get("Provider", "ollama"),
        ollama_url=raw.get("OllamaUrl", "http://localhost:11434"),
        ollama_model=raw.get("OllamaModel", "gemma3:12b"),
        temperature=float(raw.get("Temperature", 0.2)),
        max_input_chars=int(raw.get("MaxInputChars", 12000)),
        llm=LLMConfig(
            enabled=bool(llm_raw.get("enabled", False)),
            provider=str(llm_raw.get("provider", "openai_compatible") or "openai_compatible"),
            base_url=str(llm_raw.get("base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1"),
            model=str(llm_raw.get("model", "gpt-4o-mini") or "gpt-4o-mini"),
            api_key_env=str(llm_raw.get("api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY"),
            timeout=int(llm_raw.get("timeout", 60)),
            temperature=float(llm_raw.get("temperature", 0.2)),
            max_tokens=int(llm_raw.get("max_tokens", 1500)),
            max_input_chars=int(llm_raw.get("max_input_chars", 6000)),
            use_for_education_summary=bool(llm_raw.get("use_for_education_summary", True)),
            use_for_idea_cards=bool(llm_raw.get("use_for_idea_cards", False)),
            use_for_ai_diagnosis=bool(llm_raw.get("use_for_ai_diagnosis", True)),
        ),
    )
