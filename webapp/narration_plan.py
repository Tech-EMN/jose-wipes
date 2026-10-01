"""Fit per-shot narration into the requested duration ceiling before any video is generated."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

BRAND_CARD_DURATION_SECONDS = 3
NARRATION_TAIL_SECONDS = 0.5
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class DurationRange:
    min_seconds: int
    max_seconds: int

    def clamp(self, seconds: int) -> int:
        return max(self.min_seconds, min(seconds, self.max_seconds))


@dataclass(frozen=True)
class NarrationClip:
    text: str
    audio_path: Path
    duration_seconds: float


@dataclass(frozen=True)
class NarrationBudget:
    clips: tuple[NarrationClip | None, ...]
    shot_durations: tuple[int, ...]
    removed_sentences: tuple[str, ...]
    required_seconds: float


Synthesizer = Callable[[int, str], NarrationClip]


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in SENTENCE_BOUNDARY.split(text.strip()) if sentence.strip()]


def timeline_seconds_for(clip: NarrationClip | None, planned_seconds: int, duration_range: DurationRange) -> int:
    if clip is None:
        return duration_range.clamp(planned_seconds)
    return max(duration_range.min_seconds, math.ceil(clip.duration_seconds + NARRATION_TAIL_SECONDS))


def shot_duration_for(clip: NarrationClip | None, planned_seconds: int, duration_range: DurationRange) -> int:
    return duration_range.clamp(timeline_seconds_for(clip, planned_seconds, duration_range))


def _sentences_to_drop(sentences: Sequence[str], clip: NarrationClip, excess_seconds: float) -> int:
    seconds_per_char = clip.duration_seconds / max(1, len(clip.text))
    dropped = 1
    estimated_seconds = len(sentences[-1]) * seconds_per_char
    while dropped < len(sentences):
        next_seconds = len(sentences[-1 - dropped]) * seconds_per_char
        if estimated_seconds + next_seconds >= excess_seconds:
            break
        estimated_seconds += next_seconds
        dropped += 1
    return dropped


def _removal_order(sentences: Sequence[Sequence[str]]) -> list[int]:
    narrated = [index for index, shot_sentences in enumerate(sentences) if shot_sentences]
    if len(narrated) <= 1:
        return list(reversed(narrated))
    protected_last = narrated[-1]
    return list(reversed(narrated[:-1])) + [protected_last]


def fit_narration_to_budget(
    narrations: Sequence[str],
    planned_durations: Sequence[int],
    *,
    budget_seconds: float,
    duration_range: DurationRange,
    synthesize: Synthesizer,
) -> NarrationBudget:
    if len(narrations) != len(planned_durations):
        raise ValueError("narrations and planned_durations must have the same length")

    sentences = [split_sentences(text) for text in narrations]
    clips: list[NarrationClip | None] = [
        synthesize(index, " ".join(shot_sentences)) if shot_sentences else None
        for index, shot_sentences in enumerate(sentences)
    ]

    def durations(*, compact_silent_shots: bool) -> list[int]:
        return [
            duration_range.min_seconds
            if compact_silent_shots and clip is None
            else timeline_seconds_for(clip, planned, duration_range)
            for clip, planned in zip(clips, planned_durations)
        ]

    def shot_durations(timeline: Sequence[int]) -> tuple[int, ...]:
        return tuple(duration_range.clamp(seconds) for seconds in timeline)

    relaxed = durations(compact_silent_shots=False)
    required_seconds = float(sum(relaxed))
    if required_seconds <= budget_seconds:
        return NarrationBudget(tuple(clips), shot_durations(relaxed), (), required_seconds)

    removed: list[str] = []
    for shot_index in _removal_order(sentences):
        while sentences[shot_index]:
            excess = sum(durations(compact_silent_shots=True)) - budget_seconds
            if excess <= 0:
                break
            clip = clips[shot_index]
            count = _sentences_to_drop(sentences[shot_index], clip, excess) if clip else 1
            removed[0:0] = sentences[shot_index][-count:]
            del sentences[shot_index][-count:]
            remaining = " ".join(sentences[shot_index])
            clips[shot_index] = synthesize(shot_index, remaining) if remaining else None

    return NarrationBudget(
        clips=tuple(clips),
        shot_durations=shot_durations(durations(compact_silent_shots=True)),
        removed_sentences=tuple(removed),
        required_seconds=required_seconds,
    )


def budget_warning(
    budget: NarrationBudget,
    *,
    ceiling_seconds: int,
    reserved_seconds: int,
    available_ceilings: Sequence[int],
) -> str | None:
    if not budget.removed_sentences:
        return None

    needed = math.ceil(budget.required_seconds + reserved_seconds)
    removed = "; ".join(f"«{sentence}»" for sentence in budget.removed_sentences)
    larger = [ceiling for ceiling in sorted(available_ceilings) if ceiling >= needed]
    suggestion = (
        f"Use a duração de {larger[0]}s para incluir tudo."
        if larger
        else "Nem a maior duração comporta o roteiro inteiro; encurte o texto."
    )
    return (
        f"O roteiro precisa de cerca de {needed}s e não coube em {ceiling_seconds}s. "
        f"Ficaram de fora: {removed}. {suggestion}"
    )
