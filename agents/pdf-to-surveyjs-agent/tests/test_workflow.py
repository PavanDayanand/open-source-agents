from __future__ import annotations

import pytest

from pdf_to_surveyjs_agent.workflow import (
    ConfigurationError,
    ConversionError,
    _parse_model_json,
    _require_configuration,
)


def test_missing_credentials_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="No fallback model was used"):
        _require_configuration()


def test_placeholder_credential_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "your_google_ai_studio_api_key_here")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="real key"):
        _require_configuration()


def test_parse_model_json_accepts_fenced_output() -> None:
    parsed = _parse_model_json(
        '```json\n{"survey":{"elements":[]},"warnings":["Review required"]}\n```'
    )

    assert parsed["warnings"] == ["Review required"]


def test_parse_model_json_rejects_extra_wrapper_keys() -> None:
    with pytest.raises(ConversionError, match="exactly the keys"):
        _parse_model_json(
            '{"survey":{"elements":[]},"warnings":[],"unexpected":true}'
        )

