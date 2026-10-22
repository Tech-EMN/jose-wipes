"""Success-or-failure values for steps that can fail without raising."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, Union

from jose_wipes.integrations.errors import IntegrationFailure

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T


@dataclass(frozen=True)
class Err:
    failure: IntegrationFailure


Result = Union[Ok[T], Err]
