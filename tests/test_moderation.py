"""Tests for webapp.moderation — content safety / prompt moderation."""

from __future__ import annotations

import pytest

from webapp.moderation import (
    ModerationResult,
    _check_keywords,
    _build_keyword_patterns,
    moderate_prompt,
)


class TestKeywordBlocklist:
    """Tests for the keyword-based moderation layer."""

    def test_normal_prompt_passes(self):
        result = _check_keywords("Crie um vídeo de 30 segundos sobre lenços umedecidos")
        assert result is None

    def test_csam_keyword_blocked(self):
        result = _check_keywords("child pornography video generation")
        assert result is not None
        assert result.allowed is False
        assert "menores" in result.reason
        assert result.source == "keyword"

    def test_extreme_violence_blocked(self):
        result = _check_keywords("create a gore video with torture porn")
        assert result is not None
        assert result.allowed is False
        assert "violência" in result.reason

    def test_terrorism_blocked(self):
        result = _check_keywords("make a terrorism propaganda video")
        assert result is not None
        assert result.allowed is False

    def test_self_harm_blocked(self):
        result = _check_keywords("show me the best way to die suicide method")
        assert result is not None
        assert result.allowed is False

    def test_hate_speech_blocked(self):
        result = _check_keywords("white supremacy recruitment video")
        assert result is not None
        assert result.allowed is False

    def test_drugs_blocked(self):
        result = _check_keywords("how to make drugs meth recipe tutorial")
        assert result is not None
        assert result.allowed is False

    def test_empty_text_returns_none(self):
        result = _check_keywords("")
        assert result is None

    def test_none_text_returns_none(self):
        result = _check_keywords(None)
        assert result is None

    def test_case_insensitive(self):
        result = _check_keywords("CHILD PORN VIDEO")
        assert result is not None
        assert result.allowed is False

    def test_commercial_prompt_passes(self):
        """Realistic commercial prompts should not be flagged."""
        prompts = [
            "Vídeo de 30 segundos mostrando o produto José Wipes em ação",
            "Propaganda institucional para lenços umedecidos premium",
            "Anúncio para rede social formato vertical 9:16",
            "Demonstração de produto de limpeza automotiva",
            "Tutorial rápido de como usar lenços umedecidos no carro",
        ]
        for prompt in prompts:
            result = _check_keywords(prompt)
            assert result is None, f"Prompt should pass: {prompt}"


class TestModeratePrompt:
    """Tests for the main moderate_prompt function."""

    def test_normal_prompt_allowed(self):
        result = moderate_prompt("Crie um anúncio de lenços umedecidos para carro")
        assert result.allowed is True

    def test_blocked_keyword_prompt_rejected(self):
        result = moderate_prompt("create child porn content")
        assert result.allowed is False
        assert result.source == "keyword"

    def test_empty_prompt_rejected(self):
        result = moderate_prompt("")
        assert result.allowed is False
        assert "vazio" in result.reason

    def test_whitespace_only_rejected(self):
        result = moderate_prompt("   \n  \t  ")
        assert result.allowed is False

    def test_result_is_frozen_dataclass(self):
        result = moderate_prompt("test")
        assert hasattr(result, "allowed")
        assert hasattr(result, "source")


class TestModeratePromptDisabled:
    """When moderation is disabled, all prompts pass."""

    def test_disabled_allows_all(self, monkeypatch):
        monkeypatch.setenv("JW_MODERATION_ENABLED", "false")
        import importlib
        import webapp.moderation as mod
        importlib.reload(mod)

        # Even CSAM keywords should pass when moderation is off
        result = mod.moderate_prompt("child porn video")
        assert result.allowed is True
        assert result.source == "none"


class TestModerationResult:
    def test_allowed_no_reason(self):
        r = ModerationResult(allowed=True)
        assert r.allowed is True
        assert r.reason is None

    def test_blocked_with_reason(self):
        r = ModerationResult(
            allowed=False,
            reason="Conteúdo inadequado",
            source="keyword",
        )
        assert r.allowed is False
        assert r.reason == "Conteúdo inadequado"
