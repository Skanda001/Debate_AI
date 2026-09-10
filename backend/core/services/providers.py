"""
Pluggable LLM provider layer.

Each contestant in the comparison is an LLMProvider. Add a new one and it
just shows up as another column in the UI - no other code needs to change.

Configure which models actually run via the CONTESTANTS and JUDGE_MODEL
environment variables (see backend/.env.example).
"""

import os
import json
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import requests


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------
class ProviderError(Exception):
    """Raised whenever a provider can't produce an answer.

    `retry_after` (seconds, optional) tells the UI how long to wait
    before the quota resets.
    """

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


# ------------------------------------------------------------------
# Retry-after extraction helpers
# ------------------------------------------------------------------
def _extract_retry_after(resp):
    """Try several headers providers use for rate-limit reset timing."""
    if resp is None:
        return None
    headers = resp.headers or {}

    ra = headers.get("Retry-After") or headers.get("retry-after")
    if ra:
        try:
            return int(float(ra))
        except (ValueError, TypeError):
            pass

    xr = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
    if xr:
        try:
            return max(0, int(float(xr)) - int(time.time()))
        except (ValueError, TypeError):
            pass

    return None


def _seconds_until_midnight_pacific():
    """Gemini free-tier daily quotas reset at midnight Pacific Time."""
    pacific = timezone(timedelta(hours=-8))
    now_pt = datetime.now(pacific)
    next_midnight = (now_pt + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((next_midnight - now_pt).total_seconds())


def _extract_retry_after_from_text(text):
    """Parse Gemini's error strings for a reset hint."""
    if not text:
        return None
    s = str(text)

    # Daily quota — reset at midnight Pacific
    if "PerDay" in s or "per day" in s.lower():
        return _seconds_until_midnight_pacific()

    # Per-minute / per-second retry hints
    m = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", s)
    if m:
        return int(m.group(1))
    m = re.search(r"Please retry in ([\d.]+)s", s)
    if m:
        return int(float(m.group(1)))
    return None


def _is_rate_limit_error(text):
    """Best-effort detection of 429/quota errors in arbitrary strings."""
    if not text:
        return False
    s = str(text).lower()
    return (
        "429" in s
        or "rate limit" in s
        or "quota" in s
        or "resource_exhausted" in s
        or "too many requests" in s
    )


# ------------------------------------------------------------------
# Base class
# ------------------------------------------------------------------
class LLMProvider(ABC):
    id: str
    display_name: str

    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...

    def stream(self, prompt: str):
        """Default fallback: no real streaming, yield the full answer once."""
        yield self.generate(prompt)


# ------------------------------------------------------------------
# Ollama
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# Google Gemini
# ------------------------------------------------------------------
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
            msg = str(e)
            retry_after = _extract_retry_after_from_text(msg)
            if retry_after is None and _is_rate_limit_error(msg):
                retry_after = 60
            raise ProviderError(msg, retry_after=retry_after)

    def stream(self, prompt):
        try:
            model = self._genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt, stream=True)
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except Exception as e:
            msg = str(e)
            retry_after = _extract_retry_after_from_text(msg)
            if retry_after is None and _is_rate_limit_error(msg):
                retry_after = 60
            raise ProviderError(msg, retry_after=retry_after)


# ------------------------------------------------------------------
# OpenAI-compatible (OpenAI, Groq, OpenRouter, vLLM, ...)
# ------------------------------------------------------------------
class OpenAICompatProvider(LLMProvider):
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
            if resp.status_code == 429:
                raise ProviderError("429 rate limited", retry_after=_extract_retry_after(resp))
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except ProviderError:
            raise
        except Exception as e:
            msg = str(e)
            retry_after = _extract_retry_after_from_text(msg)
            if retry_after is None and _is_rate_limit_error(msg):
                retry_after = 60
            raise ProviderError(msg, retry_after=retry_after)

    def stream(self, prompt):
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "text/event-stream",
                },
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
                stream=True,
                timeout=180,
            )
            if resp.status_code == 429:
                raise ProviderError("429 rate limited", retry_after=_extract_retry_after(resp))
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except ProviderError:
            raise
        except Exception as e:
            msg = str(e)
            retry_after = _extract_retry_after_from_text(msg)
            if retry_after is None and _is_rate_limit_error(msg):
                retry_after = 60
            raise ProviderError(msg, retry_after=retry_after)


# ------------------------------------------------------------------
# Mistral
# ------------------------------------------------------------------
class MistralProvider(LLMProvider):
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
            if resp.status_code == 429:
                raise ProviderError("429 rate limited", retry_after=_extract_retry_after(resp))
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except ProviderError:
            raise
        except Exception as e:
            msg = str(e)
            retry_after = _extract_retry_after_from_text(msg)
            if retry_after is None and _is_rate_limit_error(msg):
                retry_after = 60
            raise ProviderError(msg, retry_after=retry_after)

    def stream(self, prompt):
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "text/event-stream",
                },
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
                stream=True,
                timeout=180,
            )
            if resp.status_code == 429:
                raise ProviderError("429 rate limited", retry_after=_extract_retry_after(resp))
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except ProviderError:
            raise
        except Exception as e:
            msg = str(e)
            retry_after = _extract_retry_after_from_text(msg)
            if retry_after is None and _is_rate_limit_error(msg):
                retry_after = 60
            raise ProviderError(msg, retry_after=retry_after)


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------
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
    raw = os.getenv("CONTESTANTS", "ollama:llama3.2:1b,ollama:qwen2.5:3b,ollama:phi3:mini")
    contestants = []
    for spec in [s.strip() for s in raw.split(",") if s.strip()]:
        try:
            contestants.append(_instantiate(spec))
        except ProviderError as e:
            print(f"[build_contestants] SKIPPED '{spec}': {e}")
            continue
        except Exception as e:
            print(f"[build_contestants] ERROR '{spec}': {type(e).__name__}: {e}")
            continue
    print(f"[build_contestants] Loaded {len(contestants)}: {[c.id for c in contestants]}")
    return contestants


def build_judge():
    spec = os.getenv("JUDGE_MODEL", "gemini:gemini-2.5-flash")
    try:
        return _instantiate(spec)
    except ProviderError:
        contestants = build_contestants()
        return contestants[0] if contestants else None