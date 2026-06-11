from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime
    requests = None


@dataclass(frozen=True)
class LLMSettings:
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

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "LLMSettings":
        if isinstance(config, dict):
            raw = config.get("LLM", {})
        else:
            llm_obj = getattr(config, "llm", None)
            if llm_obj is None:
                raw = {}
            else:
                raw = {
                    "enabled": getattr(llm_obj, "enabled", False),
                    "provider": getattr(llm_obj, "provider", "openai_compatible"),
                    "base_url": getattr(llm_obj, "base_url", "https://api.openai.com/v1"),
                    "model": getattr(llm_obj, "model", "gpt-4o-mini"),
                    "api_key_env": getattr(llm_obj, "api_key_env", "OPENAI_API_KEY"),
                    "timeout": getattr(llm_obj, "timeout", 60),
                    "temperature": getattr(llm_obj, "temperature", 0.2),
                    "max_tokens": getattr(llm_obj, "max_tokens", 1500),
                    "max_input_chars": getattr(llm_obj, "max_input_chars", 6000),
                    "use_for_education_summary": getattr(llm_obj, "use_for_education_summary", True),
                    "use_for_idea_cards": getattr(llm_obj, "use_for_idea_cards", False),
                    "use_for_ai_diagnosis": getattr(llm_obj, "use_for_ai_diagnosis", True),
                }
        if not isinstance(raw, dict):
            raw = {}

        def _float(value: object, default: float) -> float:
            if value is None or value == "":
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _int(value: object, default: int) -> int:
            if value is None or value == "":
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            enabled=bool(raw.get("enabled", False)),
            provider=str(raw.get("provider", "openai_compatible") or "openai_compatible").strip(),
            base_url=str(raw.get("base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1").rstrip("/"),
            model=str(raw.get("model", "gpt-4o-mini") or "gpt-4o-mini").strip(),
            api_key_env=str(raw.get("api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY").strip(),
            timeout=_int(raw.get("timeout", 60), 60),
            temperature=_float(raw.get("temperature", 0.2), 0.2),
            max_tokens=_int(raw.get("max_tokens", 1500), 1500),
            max_input_chars=_int(raw.get("max_input_chars", 6000), 6000),
            use_for_education_summary=bool(raw.get("use_for_education_summary", True)),
            use_for_idea_cards=bool(raw.get("use_for_idea_cards", False)),
            use_for_ai_diagnosis=bool(raw.get("use_for_ai_diagnosis", True)),
        )


@dataclass
class LLMResult:
    text: str
    raw_response: str


class LLMClient:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.settings = LLMSettings.from_config(config)
        self.disabled_for_session = False

    def _api_key(self) -> str:
        if not self.settings.api_key_env:
            return ""
        return os.environ.get(self.settings.api_key_env, "").strip()

    def _disable_for_session(self, reason: str) -> None:
        self.disabled_for_session = True
        print(f"[llm] {reason} disabled for this run; using fallback")

    def _is_auth_or_quota_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return any(
            token in text
            for token in [
                "429",
                "too many requests",
                "rate limit",
                "insufficient_quota",
                "quota",
                "billing",
                "invalid_api_key",
                "authentication",
                "unauthorized",
                "403",
                "401",
                "402",
            ]
        )

    def can_use_education_summary(self) -> bool:
        return self.settings.use_for_education_summary and self.is_enabled()

    def can_use_idea_cards(self) -> bool:
        return self.settings.use_for_idea_cards and self.is_enabled()

    def can_use_ai_diagnosis(self) -> bool:
        return self.settings.use_for_ai_diagnosis and self.is_enabled()

    def is_enabled(self) -> bool:
        if self.disabled_for_session:
            return False
        if not self.settings.enabled:
            return False
        if self.settings.provider != "openai_compatible":
            return False
        if not self.settings.api_key_env:
            return False
        if not self._api_key():
            return False
        return True

    def status_lines(self) -> list[str]:
        lines = [f"[llm] config enabled: {str(self.settings.enabled).lower()}"]
        if self.settings.enabled:
            lines.append(f"[llm] provider: {self.settings.provider}")
            lines.append(f"[llm] api key env: {self.settings.api_key_env}")
            lines.append(f"[llm] api key found: {str(bool(self._api_key())).lower()}")
            if self.is_enabled():
                lines.append(f"[llm] enabled: true, model: {self.settings.model}")
            elif self.disabled_for_session:
                lines.append("[llm] disabled for this run after previous API failure; using fallback")
            else:
                lines.append("[llm] enabled: false, using rule-based fallback")
        else:
            lines.append("[llm] enabled: false, using rule-based fallback")
        return lines

    def status_line(self) -> str:
        return self.status_lines()[-1]

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if self.disabled_for_session:
            print("[llm] disabled for this run after previous API failure; using fallback")
            return ""
        if not self.is_enabled():
            return ""

        api_key = self._api_key()
        if not api_key:
            return ""

        if requests is None:
            print("[llm] request failed, using fallback: requests package not installed")
            return ""

        url = f"{self.settings.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.settings.timeout)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", []) if isinstance(data, dict) else []
            if not choices:
                print("[llm] request failed, using fallback: empty choices")
                return ""
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = str(message.get("content", "") or "").strip()
            if not content:
                print("[llm] request failed, using fallback: empty content")
                return ""
            return content
        except Exception as exc:  # pragma: no cover - runtime/network failures
            if self._is_auth_or_quota_error(exc):
                self._disable_for_session("rate limit or quota exceeded.")
                print("[llm] check API billing, project limits, or reduce LLM calls.")
                return ""
            print(f"[llm] request failed, using fallback: {exc}")
            return ""

    def generate_text(self, prompt: str, *, task_name: str = "generic") -> LLMResult:
        text = self.chat(f"Task: {task_name}", prompt)
        if not text:
            text = (
                f"LLM 연동이 비활성화된 상태입니다. task={task_name}, "
                f"provider={self.settings.provider}, model={self.settings.model}"
            )
        return LLMResult(text=text, raw_response=text)

    def generate_json(self, prompt: str, *, task_name: str = "json_task") -> LLMResult:
        text = self.chat(f"Task: {task_name}", prompt)
        if text:
            return LLMResult(text=text, raw_response=text)

        response = {
            "task": task_name,
            "provider": self.settings.provider,
            "note": "LLM 연동이 비활성화된 상태입니다.",
        }
        text = json.dumps(response, ensure_ascii=False)
        return LLMResult(text=text, raw_response=text)


def to_plain_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    return {"value": obj}
