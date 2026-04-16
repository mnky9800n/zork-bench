"""Tests for the harness resilience layer.

Three things to pin:
  1. _is_retriable_llm_error correctly classifies common SDK exception shapes.
  2. _call_llm_with_retry retries on transient errors, gives up on non-retriable
     errors immediately, and re-raises after exhausting attempts.
  3. GameSessionError is a real exception class that can be raised and caught
     across the session/agent boundary.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zork_harness.agent import _call_llm_with_retry, _is_retriable_llm_error
from zork_harness.session import GameSessionError


# ---------------------------------------------------------------------------
# Synthetic exception classes that mimic SDK shapes
# ---------------------------------------------------------------------------

class _FakeBadRequestError(Exception):
    """Mimics anthropic.BadRequestError / openai.BadRequestError (400)."""
    status_code = 400


class _FakeAuthenticationError(Exception):
    """Mimics auth failures (401)."""
    status_code = 401


class _FakeRateLimitError(Exception):
    """Mimics rate limits (429)."""
    status_code = 429


class _FakeInternalServerError(Exception):
    """Mimics 5xx (retriable)."""
    status_code = 500


class _FakeAPIError(Exception):
    """Mimics SDK APIError without an explicit status code."""


class _FakeAPIConnectionError(Exception):
    """Mimics connection failures."""


class _NotAnLLMError(Exception):
    """Some random unrelated exception."""


# ---------------------------------------------------------------------------
# _is_retriable_llm_error
# ---------------------------------------------------------------------------

def test_bad_request_is_not_retriable():
    assert not _is_retriable_llm_error(_FakeBadRequestError("credits exhausted"))


def test_authentication_is_not_retriable():
    assert not _is_retriable_llm_error(_FakeAuthenticationError("bad key"))


def test_rate_limit_is_retriable():
    assert _is_retriable_llm_error(_FakeRateLimitError("slow down"))


def test_5xx_is_retriable():
    assert _is_retriable_llm_error(_FakeInternalServerError("oops"))


def test_apierror_class_name_is_retriable():
    assert _is_retriable_llm_error(_FakeAPIError("server had an error"))


def test_connection_error_is_retriable():
    assert _is_retriable_llm_error(_FakeAPIConnectionError("network blip"))


def test_unknown_exception_is_not_retriable():
    """Default-deny for unfamiliar errors so real bugs are not masked."""
    assert not _is_retriable_llm_error(_NotAnLLMError("???"))


# ---------------------------------------------------------------------------
# _call_llm_with_retry
# ---------------------------------------------------------------------------

def test_retry_succeeds_on_first_attempt():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert _call_llm_with_retry(fn) == "ok"
    assert calls["n"] == 1


def test_retry_succeeds_after_transient_then_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _FakeInternalServerError("transient")
        return "ok"

    with patch("zork_harness.agent.time.sleep"):  # do not actually sleep in tests
        result = _call_llm_with_retry(fn, max_attempts=3, base_delay=0.01)

    assert result == "ok"
    assert calls["n"] == 2


def test_retry_reraises_non_retriable_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _FakeBadRequestError("credits exhausted")

    with patch("zork_harness.agent.time.sleep"):
        with pytest.raises(_FakeBadRequestError):
            _call_llm_with_retry(fn, max_attempts=5)

    assert calls["n"] == 1  # no retries on non-retriable error


def test_retry_gives_up_after_max_attempts():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _FakeInternalServerError("still broken")

    with patch("zork_harness.agent.time.sleep"):
        with pytest.raises(_FakeInternalServerError):
            _call_llm_with_retry(fn, max_attempts=3, base_delay=0.01)

    assert calls["n"] == 3


def test_retry_passes_args_and_kwargs_through():
    seen = {}

    def fn(a, b, *, c):
        seen["a"], seen["b"], seen["c"] = a, b, c
        return a + b + c

    assert _call_llm_with_retry(fn, 1, 2, c=3) == 6
    assert seen == {"a": 1, "b": 2, "c": 3}


# ---------------------------------------------------------------------------
# GameSessionError
# ---------------------------------------------------------------------------

def test_game_session_error_is_an_exception():
    """Catching the typed exception is the contract that lets a future
    Z-machine emulator drop in without changing the agent loop."""
    with pytest.raises(GameSessionError):
        raise GameSessionError("game died")


def test_game_session_error_carries_message():
    try:
        raise GameSessionError("Game process ended unexpectedly (EOF).")
    except GameSessionError as exc:
        assert "EOF" in str(exc)
