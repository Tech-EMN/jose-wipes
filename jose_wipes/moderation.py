"""Content safety / prompt moderation for the José Wipes Web Video Studio.

Checks user-submitted prompts before they reach external APIs (OpenAI,
Higgsfield, ElevenLabs) to prevent policy violations that could result
in account bans.

Two-layer approach:
    1. Keyword blocklist (fast, no API call, catches obvious violations)
    2. OpenAI Moderation endpoint (API-based, catches nuanced violations)

Environment variables:
    JW_MODERATION_ENABLED: set to "false" to disable (default: "true")
    JW_MODERATION_OPENAI: use OpenAI Moderation API (default: "true" when OPENAI_API_KEY is set)
    JW_MODERATION_STRICT: block on any flagged category (default: "false" — block only on severe)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger(__name__)

# ---- Configuration ----
_MODERATION_ENABLED = os.getenv("JW_MODERATION_ENABLED", "true").strip().lower() not in {
    "false", "0", "no", "off",
}
_MODERATION_OPENAI = os.getenv("JW_MODERATION_OPENAI", "true").strip().lower() not in {
    "false", "0", "no", "off",
}
_MODERATION_STRICT = os.getenv("JW_MODERATION_STRICT", "false").strip().lower() in {
    "true", "1", "yes", "sim",
}

# Categories from OpenAI Moderation that should ALWAYS trigger rejection
_SEVERE_CATEGORIES = frozenset({
    "sexual/minors",
    "sexual",
    "hate/threatening",
    "violence/graphic",
    "self-harm/intent",
    "self-harm/instructions",
    "harassment/threatening",
})

# Additional categories blocked in strict mode
_STRICT_CATEGORIES = frozenset({
    "hate",
    "violence",
    "self-harm",
    "harassment",
    "illicit",
    "illicit/violent",
})

# ---- Keyword Blocklist ----
# Blocklist compiled from common policy violation patterns.
# These are checked BEFORE any API call — instant rejection.

_KEYWORD_PATTERNS: list[tuple[re.Pattern, str]] = []

def _build_keyword_patterns() -> list[tuple[re.Pattern, str]]:
    """Build compiled regex patterns from the keyword blocklist."""
    patterns: list[tuple[re.Pattern, str]] = []
    # Each entry: (regex pattern, reason for blocking)
    raw_patterns = [
        # CSAM / minors
        (r'\b(child\s*porn|cp\b|underage|csa[mr]?|pedo)', "conteúdo envolvendo menores"),
        # Extreme violence / gore
        (r'\b(gore|torture\s*porn|snuff|mutilation\s*fetish)', "violência gráfica extrema"),
        # Illegal content
        (r'\b(terroris[mt]|bomb\s*making|how\s*to\s*make\s*(a\s*)?bomb)', "conteúdo ilegal/terrorismo"),
        # Self-harm instructions
        (r'\b(suicide\s*method|how\s*to\s*kill\s*yourself|best\s*way\s*to\s*die)', "instruções de autoagressão"),
        # Hate speech
        (r'\b(lynch\s*(ing)?\b|genocide\s*denial|white\s*supremac)', "discurso de ódio"),
        # Drugs
        (r'\b(meth\s*recipe|crack\s*cocaine\s*recipe|how\s*to\s*make\s*drugs)', "instruções de drogas ilegais"),
    ]
    for pattern, reason in raw_patterns:
        patterns.append((re.compile(pattern, re.IGNORECASE), reason))
    return patterns

_KEYWORD_PATTERNS = _build_keyword_patterns()


@dataclass(frozen=True)
class ModerationResult:
    """Result of a content moderation check."""

    allowed: bool
    reason: str | None = None
    categories: list[str] | None = None
    source: str = "none"  # "keyword", "openai", "none"


def _check_keywords(text: str) -> ModerationResult | None:
    """Check text against keyword blocklist. Returns ModerationResult if flagged."""
    if not text:
        return None
    lowered = text.lower()
    for pattern, reason in _KEYWORD_PATTERNS:
        if pattern.search(lowered):
            _log.warning("Keyword blocklist hit: '%s' matched in prompt", reason)
            return ModerationResult(
                allowed=False,
                reason=f"Prompt bloqueado: detectado {reason}.",
                source="keyword",
            )
    return None


def _check_openai_moderation(text: str) -> ModerationResult | None:
    """Check text using OpenAI Moderation endpoint. Returns ModerationResult if flagged."""
    try:
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not openai_key:
            _log.debug("OPENAI_API_KEY not set, skipping OpenAI moderation")
            return None

        from openai import OpenAI
        client = OpenAI(api_key=openai_key, timeout=10.0)

        response = client.moderations.create(
            model="omni-moderation-latest",
            input=text,
        )

        result = response.results[0] if response.results else None
        if not result or not result.flagged:
            return None

        flagged_categories = []
        categories = result.categories

        # Check severe categories first
        for cat in _SEVERE_CATEGORIES:
            score = getattr(categories, cat.replace("/", "_").replace("-", "_"), None)
            if score is True or (isinstance(score, (int, float)) and score > 0.5):
                flagged_categories.append(cat)

        # In strict mode, check additional categories
        if _MODERATION_STRICT:
            for cat in _STRICT_CATEGORIES:
                if cat in flagged_categories:
                    continue
                score = getattr(categories, cat.replace("/", "_").replace("-", "_"), None)
                if score is True or (isinstance(score, (int, float)) and score > 0.5):
                    flagged_categories.append(cat)

        if flagged_categories:
            cats_str = ", ".join(flagged_categories)
            _log.warning(
                "OpenAI moderation flagged: categories=%s, prompt_len=%d",
                cats_str, len(text),
            )
            return ModerationResult(
                allowed=False,
                reason=(
                    f"Conteúdo bloqueado pela moderação automática "
                    f"(categorias: {cats_str}). Revise o prompt e tente novamente."
                ),
                categories=flagged_categories,
                source="openai",
            )

        return None

    except ImportError:
        _log.debug("OpenAI package not available, skipping moderation API")
        return None
    except Exception as exc:
        _log.error("OpenAI moderation check failed (non-blocking): %s", exc)
        return None  # Don't block on moderation failure — fail open


def moderate_prompt(prompt: str) -> ModerationResult:
    """Run content moderation on a user-submitted prompt.

    Returns ModerationResult with allowed=True if the prompt passes all checks,
    or allowed=False with a reason if it's blocked.
    """
    if not _MODERATION_ENABLED:
        return ModerationResult(allowed=True, source="none")

    if not prompt or not prompt.strip():
        return ModerationResult(
            allowed=False,
            reason="O prompt não pode estar vazio.",
            source="keyword",
        )

    # Layer 1: Keyword blocklist (fast, no API call)
    keyword_result = _check_keywords(prompt)
    if keyword_result is not None:
        return keyword_result

    # Layer 2: OpenAI Moderation API
    if _MODERATION_OPENAI:
        openai_result = _check_openai_moderation(prompt)
        if openai_result is not None:
            return openai_result

    return ModerationResult(allowed=True, source="none")


def moderate_prompt_sync(prompt: str) -> ModerationResult:
    """Synchronous wrapper for moderate_prompt (used in sync contexts)."""
    return moderate_prompt(prompt)
