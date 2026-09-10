"""
Pluggable LLM provider layer.

Each contestant in the comparison is an LLMProvider. Add a new one and it
just shows up as another column in the UI - no other code needs to change.

Configure which models actually run via the CONTESTANTS and JUDGE_MODEL
environment variables (see backend/.env.example).
"""

import os
import json
from abc import ABC, abstractmethod

import requests


class ProviderError(Exception):
    """Raised whenever a provider can't produce an answer."""


class LLMProvider(ABC):
    id: str
    display_name: str

    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...

    def stream(self, prompt: str):
        """Default fallback: no real streaming, yield the full answer once."""
        yield self.generate(prompt)


class OllamaProvider(LLMProvider):
    def __init__(self, model_name, display_name=None, base_url=None):
        self.model_name = model_name
        self.id = f"ollama:{model_name}"
        self.display_name = display_name or model_name
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def generate(self, prompt):
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model_name, "prompt": prompt, "stream": False},
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as e:
            raise ProviderError(str(e))

    def stream(self, prompt):
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model_name, "prompt": prompt, "stream": True},
                stream=True,
                timeout=180,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                data = json.loads(line.decode("utf-8"))
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break
        except Exception as e:
            raise ProviderError(str(e))


class GeminiProvider(LLMProvider):
    def __init__(self, model_name="gemini-2.5-flash", display_name=None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ProviderError("GEMINI_API_KEY not set")
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self.model_name = model_name
        self.id = f"gemini:{model_name}"
        self.display_name = display_name or f"Gemini {model_name}"

    def generate(self, prompt):
        try:
            model = self._genai.GenerativeModel(self.model_name)
            resp = model.generate_content(prompt)
            return (resp.text or "").strip()
        except Exception as e:
            raise ProviderError(str(e))


class OpenAICompatProvider(LLMProvider):
    """Works with any OpenAI-compatible /chat/completions endpoint
    (OpenAI itself, Groq, OpenRouter, local vLLM servers, etc.)."""

    def __init__(self, model_name, display_name=None, api_key_env="OPENAI_API_KEY", base_url=None):
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ProviderError(f"{api_key_env} not set")
        self.model_name = model_name
        self.id = f"openai:{model_name}"
        self.display_name = display_name or model_name
        self.api_key = api_key
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def generate(self, prompt):
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model_name, "messages": [{"role": "user", "content": prompt}]},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise ProviderError(str(e))


class MistralProvider(LLMProvider):
    """Mistral's API is OpenAI-compatible in shape, so this reuses the same
    request/response format but talks to Mistral's own endpoint and key."""

    def __init__(self, model_name="mistral-small-latest", display_name=None):
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ProviderError("MISTRAL_API_KEY not set")
        self.model_name = model_name
        self.id = f"mistral:{model_name}"
        self.display_name = display_name or f"Mistral {model_name}"
        self.api_key = api_key
        self.base_url = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    def generate(self, prompt):
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model_name, "messages": [{"role": "user", "content": prompt}]},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise ProviderError(str(e))


def _instantiate(spec):
    """spec looks like 'ollama:llama3.2:1b' or 'gemini:gemini-2.5-flash'."""
    kind, _, rest = spec.partition(":")
    if kind == "ollama":
        return OllamaProvider(model_name=rest)
    if kind == "gemini":
        return GeminiProvider(model_name=rest or "gemini-2.5-flash")
    if kind == "openai":
        return OpenAICompatProvider(model_name=rest)
    if kind == "mistral":
        return MistralProvider(model_name=rest or "mistral-small-latest")
    raise ProviderError(f"Unknown provider kind: {kind}")


def build_contestants():
    """
    Reads CONTESTANTS from the environment - a comma separated list of
    provider:model specs. Any contestant that fails to initialise (missing
    key, etc.) is silently skipped so the app degrades gracefully instead
    of crashing the whole comparison.
    """
    raw = os.getenv("CONTESTANTS", "ollama:llama3.2:1b,ollama:qwen2.5:3b,ollama:phi3:mini")
    contestants = []
    for spec in [s.strip() for s in raw.split(",") if s.strip()]:
        try:
            contestants.append(_instantiate(spec))
        except ProviderError:
            continue
    return contestants


def build_judge():
    """
    The judge should ideally be independent of / stronger than the
    contestants so it isn't grading its own homework. Falls back to the
    first available contestant if no judge is configured.
    """
    spec = os.getenv("JUDGE_MODEL", "gemini:gemini-2.5-flash")
    try:
        return _instantiate(spec)
    except ProviderError:
        contestants = build_contestants()
        return contestants[0] if contestants else None