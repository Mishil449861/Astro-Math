"""
ai_provider.py — picks the language model that writes readings.

Order of preference:
  1. The provider named in settings (`provider = "..."`), if its key is filled in.
  2. Otherwise the first API key that is filled in: Anthropic (Claude), Gemini, Groq.
  3. Otherwise a local Ollama model, if Ollama is running on this computer.
  4. Otherwise none, and the app hides the AI reading.

Settings come from the [ai] table of .streamlit/secrets.toml (on Streamlit Community Cloud,
paste the same text into the app's Secrets settings), or from the environment variables
ANTHROPIC_API_KEY, GEMINI_API_KEY and GROQ_API_KEY.

Only the app's calculated fact sheet and the person's question are sent: no name, birth
date or birthplace.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

SECRETS = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
OLLAMA_URL = "http://localhost:11434"

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "gemini": "gemini-3.5-flash",            # check Google's model list; change `model` if renamed
    "groq": "llama-3.3-70b-versatile",
    "ollama": "qwen3:14b",
}
NAMES = {"anthropic": "Claude (Anthropic)", "gemini": "Gemini (Google)", "groq": "Groq",
         "ollama": "a local model"}
KEY_FIELDS = {"anthropic": "anthropic_api_key", "gemini": "gemini_api_key", "groq": "groq_api_key"}
ENV_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}
# Claude models that accept server-side refusal fallbacks
CLAUDE_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class ProviderError(RuntimeError):
    """A readable reason the model couldn't answer (bad key, limit reached, offline …)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code                  # HTTP status when there was one


# Each Gemini model has its own free-tier daily allowance (gemini-3.5-flash allows only ~20
# requests a day), so when one is used up or busy the next is tried.
GEMINI_FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def load_settings() -> dict:
    cfg: dict = {}
    if SECRETS.exists():
        try:
            import tomllib
            with open(SECRETS, "rb") as f:
                cfg = dict(tomllib.load(f).get("ai", {}))
        except Exception:
            cfg = {}
    else:
        try:                                   # Streamlit Community Cloud keeps secrets here
            import streamlit as st
            if "ai" in st.secrets:
                cfg = dict(st.secrets["ai"])
        except Exception:
            pass
    for name, var in ENV_KEYS.items():
        if os.environ.get(var):
            cfg[KEY_FIELDS[name]] = os.environ[var]
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in cfg.items()}


def ollama_models(timeout: float = 0.5) -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.loads(r.read())["models"]]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class Provider:
    def __init__(self, name: str, model: str | None = None, key: str | None = None):
        self.name, self.key = name, key
        self.model = model or DEFAULT_MODELS[name]
        self.label = f"{name}:{self.model}" if name != "ollama" else self.model
        self.answered_by = self.model         # the model that wrote the last answer (Gemini may fall back)

    @property
    def privacy_note(self) -> str:
        if self.name == "ollama":
            return f"Written by {self.model} running on this computer; nothing leaves it."
        note = (f"Written by {NAMES[self.name]} ({self.model}). Only the calculated chart facts and your "
                f"question are sent to {NAMES[self.name]}, not your name, birth date or place.")
        if self.name == "gemini":
            note += " On Google's free tier, Google may use what is sent to improve its products."
        return note

    def call(self, system: str, user: str) -> str:
        return getattr(self, f"_{self.name}")(system, user)

    # ---- Claude: official SDK -------------------------------------------------
    def _anthropic(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError("The anthropic package is not installed (pip install anthropic).") from e
        client = anthropic.Anthropic(api_key=self.key)
        req = dict(model=self.model, max_tokens=16000, system=system,
                   messages=[{"role": "user", "content": user}])
        try:
            if self.model in CLAUDE_FALLBACK_MODELS:
                # if a safety classifier declines, the API retries on a fallback model itself
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                   fallbacks="default", **req)
            else:
                resp = client.messages.create(**req)
        except anthropic.AuthenticationError as e:
            raise ProviderError("The Anthropic API key was rejected.") from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError("This Anthropic API key can't use that model.") from e
        except anthropic.NotFoundError as e:
            raise ProviderError(f"Anthropic doesn't recognise the model '{self.model}'.") from e
        except anthropic.RateLimitError as e:
            raise ProviderError("The Anthropic usage limit was reached; try again later.") from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"Anthropic returned an error ({e.status_code}).") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("Couldn't reach Anthropic; check the internet connection.") from e
        if resp.stop_reason == "refusal":
            raise ProviderError("The model declined to answer this request.")
        return "".join(b.text for b in resp.content if b.type == "text")

    # ---- Gemini, Groq, Ollama: plain HTTPS ------------------------------------
    def _gemini(self, system: str, user: str) -> str:
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.4}}
        models = list(dict.fromkeys([self.model] + GEMINI_FALLBACK_MODELS))
        for i, model in enumerate(models):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                data = _post(url, body, {"x-goog-api-key": self.key}, "Gemini")
                self.answered_by = model
                break
            except ProviderError as e:
                # daily allowance used up (429) or servers busy (503): try the next model
                if e.code not in (429, 503) or i == len(models) - 1:
                    raise
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise ProviderError("Gemini returned no text (the request may have been blocked).") from e

    def _groq(self, system: str, user: str) -> str:
        body = {"model": self.model, "temperature": 0.4,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        data = _post("https://api.groq.com/openai/v1/chat/completions", body,
                     {"Authorization": f"Bearer {self.key}"}, "Groq")
        return data["choices"][0]["message"]["content"]

    def _ollama(self, system: str, user: str) -> str:
        body = {"model": self.model, "stream": False, "think": False,
                "options": {"temperature": 0.4, "num_ctx": 8192},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        return _post(f"{OLLAMA_URL}/api/chat", body, {}, "Ollama", timeout=900)["message"]["content"]


def _post(url: str, body: dict, headers: dict, who: str, timeout: float = 120) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        reason = {400: "rejected the request (check the model name)", 401: "rejected the API key",
                  403: "rejected the API key", 404: "doesn't recognise the model",
                  429: "usage limit reached; try again later"}.get(e.code, f"returned an error ({e.code})")
        raise ProviderError(f"{who} {reason}.", e.code) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ProviderError(f"Couldn't reach {who}.") from e


def get_provider(settings: dict | None = None) -> Provider | None:
    cfg = load_settings() if settings is None else settings
    chosen = (cfg.get("provider") or "").lower()
    order = [chosen] if chosen else ["anthropic", "gemini", "groq", "ollama"]
    for name in order:
        if name in KEY_FIELDS and cfg.get(KEY_FIELDS[name]):
            return Provider(name, cfg.get("model") or None, cfg[KEY_FIELDS[name]])
        if name == "ollama":
            model = pick_ollama_model(cfg.get("ollama_model"), ollama_models())
            if model:
                return Provider("ollama", model)
    return None


# Used when the configured local model isn't installed: the best one that is
OLLAMA_PREFERENCE = ["qwen3:14b", "qwen3:30b", "qwen3:8b", "gemma3:12b", "llama3.1:8b", "qwen3:4b", "gemma3:4b"]


def pick_ollama_model(wanted: str | None, installed: list[str]) -> str | None:
    if wanted and wanted in installed:
        return wanted
    for m in OLLAMA_PREFERENCE:
        if m in installed:
            return m
    chat = [m for m in installed if not any(w in m for w in ("embed", "coder", "vl"))]
    return chat[0] if chat else None
