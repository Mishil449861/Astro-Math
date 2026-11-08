"""
How the app picks a model. No network calls: settings are passed in directly.
Run:  python -m pytest tests
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_provider as ap  # noqa: E402


def test_first_filled_key_wins():
    p = ap.get_provider({"gemini_api_key": "g", "groq_api_key": "q", "anthropic_api_key": ""})
    assert (p.name, p.key, p.model) == ("gemini", "g", ap.DEFAULT_MODELS["gemini"])


def test_named_provider_and_model_override():
    p = ap.get_provider({"provider": "groq", "gemini_api_key": "g", "groq_api_key": "q", "model": "m1"})
    assert (p.name, p.key, p.model) == ("groq", "q", "m1")


def test_anthropic_key_and_privacy_note():
    p = ap.get_provider({"anthropic_api_key": "a"})
    assert p.name == "anthropic" and p.model == "claude-opus-5-5"
    assert "not your name, birth date or place" in p.privacy_note


def test_named_provider_without_key_gives_none():
    assert ap.get_provider({"provider": "gemini", "groq_api_key": "q"}) is None


def test_secrets_file_is_ignored_by_git():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".gitignore"), encoding="utf-8") as f:
        assert ".streamlit/secrets.toml" in f.read().split()


def test_local_model_auto_pick():
    assert ap.pick_ollama_model("", ["qwen2.5-coder:1.5b", "qwen3:8b", "nomic-embed-text:latest"]) == "qwen3:8b"
    assert ap.pick_ollama_model("mistral:7b", ["qwen3:14b", "mistral:7b"]) == "mistral:7b"
    assert ap.pick_ollama_model("", ["nomic-embed-text:latest", "mistral:7b"]) == "mistral:7b"
    assert ap.pick_ollama_model("", ["nomic-embed-text:latest"]) is None


def test_gemini_falls_back_when_a_model_is_used_up(monkeypatch):
    tried = []

    def fake_post(url, body, headers, who, timeout=120):
        model = url.split("/models/")[1].split(":")[0]
        tried.append(model)
        if model == "gemini-3.5-flash":
            raise ap.ProviderError("Gemini usage limit reached; try again later.", 429)
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    monkeypatch.setattr(ap, "_post", fake_post)
    p = ap.Provider("gemini", "gemini-3.5-flash", "k")
    assert p.call("s", "u") == "ok"
    assert tried == ["gemini-3.5-flash", "gemini-3.5-flash-lite"] and p.answered_by == "gemini-3.5-flash-lite"

    # a bad key is not retried on other models
    tried.clear()
    monkeypatch.setattr(ap, "_post", lambda *a, **k: (_ for _ in ()).throw(
        ap.ProviderError("Gemini rejected the API key.", 401)))
    try:
        p.call("s", "u")
        assert False, "should have raised"
    except ap.ProviderError as e:
        assert e.code == 401
    assert "free tier" in p.privacy_note
