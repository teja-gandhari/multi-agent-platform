"""Single entry point for every LLM request made by NexusAI.

Why this exists
---------------
Previously each agent built its own OpenAI client, retried *every* failure
(including 400/401/404) and flattened errors into strings that the workflow
later pattern-matched. This module replaces that with:

* one client factory (Gemini's OpenAI-compatible endpoint),
* a typed error (:class:`LLMError`) with a stable ``code``,
* a retry policy that depends on the error type,
* per-call logging (duration, finish reason, token usage),
* secret redaction in every message that can reach the console.

Retry policy (all bounded)
--------------------------
=================  =====================================================
AUTH / MODEL /     never retried - retrying cannot fix them
BAD_REQUEST /
QUOTA (daily or
``limit: 0``)
RATE_LIMIT         waits for the provider's ``retryDelay`` (<= 70 s),
                   at most 2 waits, then stops
TIMEOUT /          one retry after a short pause, then stops
CONNECTION / SERVER
=================  =====================================================
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from config import settings

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

# Codes where re-running the *agent* (not just the HTTP call) can help,
# because the problem is the model's output rather than the environment.
OUTPUT_PROBLEM_CODES = {"EMPTY", "TRUNCATED", "MALFORMED"}

HINTS = {
    "MISSING_KEY": "Add GEMINI_API_KEY to the .env file in the project root.",
    "AUTH": (
        "The API key was rejected. Create a new key in Google AI Studio, "
        "update .env, and make sure no stale GEMINI_API_KEY is set in the "
        "Windows environment."
    ),
    "MODEL_NOT_FOUND": (
        "The model name is not available to this key on this endpoint. "
        "Run `python diagnose_llm.py` to test it, or set *_MODEL in .env "
        "to a model listed at https://ai.google.dev/gemini-api/docs/models."
    ),
    "BAD_REQUEST": "The provider rejected the request format (see detail).",
    "QUOTA": (
        "The free-tier quota for this model is exhausted (or is 0 for this "
        "key). Wait for the reset (daily quotas reset at midnight Pacific "
        "time), check your limits in Google AI Studio, or set a different "
        "model in .env. Do not enable billing unless you intend to."
    ),
    "RATE_LIMIT": (
        "Per-minute rate limit still exceeded after waiting. Wait a minute "
        "and run again."
    ),
    "TIMEOUT": (
        "No response arrived in time. Check your network/proxy, try again, "
        "or raise LLM_TIMEOUT_SECONDS in .env. Run `python diagnose_llm.py` "
        "to see which endpoint is slow."
    ),
    "CONNECTION": (
        "Could not reach generativelanguage.googleapis.com. Check internet, "
        "VPN, proxy or firewall settings."
    ),
    "SERVER": "Google's service returned a server error. Try again later.",
    "EMPTY": "The model returned no text (possibly all budget spent on thinking).",
    "TRUNCATED": "The model's output hit the token limit.",
    "MALFORMED": "The model returned a response that could not be parsed.",
    "UNKNOWN": "Unexpected API failure (see detail).",
}


class LLMError(RuntimeError):
    """A classified failure from the LLM provider."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        detail: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.detail = detail
        self.retry_after = retry_after

    @property
    def fatal(self) -> bool:
        """True when re-running the agent will not help."""
        return self.code not in OUTPUT_PROBLEM_CODES

    def __str__(self) -> str:  # include the code so logs are unambiguous
        base = super().__str__()
        return f"[{self.code}] {base}"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _redact(text: str) -> str:
    key = settings.api_key()
    if key and key in text:
        text = text.replace(key, "***")
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "***", text)


def _error_text(exc: BaseException) -> str:
    """Best-effort readable text of a provider error (never the key)."""
    parts: list[str] = []
    body = getattr(exc, "body", None)
    if body:
        try:
            parts.append(json.dumps(body)[:1500])
        except (TypeError, ValueError):
            parts.append(str(body)[:1500])
    parts.append(str(exc))
    return _redact(" | ".join(p for p in parts if p))[:2000]


def _mro_names(exc: BaseException) -> list[str]:
    return [cls.__name__ for cls in type(exc).__mro__]


_RETRY_DELAY_PATTERNS = (
    re.compile(r"retryDelay\W+(\d+(?:\.\d+)?)\s*s", re.I),
    re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.I),
    re.compile(r"retry after (\d+(?:\.\d+)?)", re.I),
)


def _parse_retry_delay(text: str, exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            value = headers.get("retry-after")
            if value:
                return float(value)
        except (TypeError, ValueError):
            pass
    for pattern in _RETRY_DELAY_PATTERNS:
        match = pattern.search(text)
        if match:
            return float(match.group(1))
    return None


def classify_exception(exc: BaseException) -> LLMError:
    """Map any SDK/network exception to an :class:`LLMError`."""
    if isinstance(exc, LLMError):
        return exc

    names = _mro_names(exc)
    status = getattr(exc, "status_code", None)
    text = _error_text(exc)
    low = text.lower()

    if status is None:
        if any("timeout" in n.lower() for n in names):
            return LLMError("TIMEOUT", "The API request timed out.", detail=text)
        if any("connection" in n.lower() for n in names):
            return LLMError("CONNECTION", "Could not connect to the API.", detail=text)
        return LLMError("UNKNOWN", f"{type(exc).__name__}: {text}", detail=text)

    if status in (401, 403) or "api key not valid" in low or "api_key_invalid" in low:
        return LLMError("AUTH", f"Authentication/permission failed (HTTP {status}).",
                        status=status, detail=text)
    if status == 404:
        return LLMError("MODEL_NOT_FOUND", "Model or endpoint not found (HTTP 404).",
                        status=status, detail=text)
    if status == 429:
        retry_after = _parse_retry_delay(text, exc)
        daily = any(m in low for m in ("perday", "per day", "requests per day", "daily"))
        zero = re.search(r"limit:\s*0\b", low) is not None
        if daily or zero:
            return LLMError("QUOTA", "Free-tier quota exhausted (HTTP 429).",
                            status=status, detail=text, retry_after=retry_after)
        return LLMError("RATE_LIMIT", "Rate limit reached (HTTP 429).",
                        status=status, detail=text, retry_after=retry_after)
    if status in (408, 504):
        return LLMError("TIMEOUT", f"The API timed out (HTTP {status}).",
                        status=status, detail=text)
    if status == 400:
        return LLMError("BAD_REQUEST", "The API rejected the request (HTTP 400).",
                        status=status, detail=text)
    if status >= 500:
        return LLMError("SERVER", f"Provider server error (HTTP {status}).",
                        status=status, detail=text)
    return LLMError("UNKNOWN", f"Unexpected HTTP {status}.", status=status, detail=text)


def explain(err: LLMError) -> str:
    """Human-readable, secret-free explanation for console/state."""
    hint = HINTS.get(err.code, "")
    detail = f" Detail: {err.detail[:400]}" if err.detail else ""
    return f"{err}. {hint}{detail}".strip()


# --------------------------------------------------------------------------
# Client + call log
# --------------------------------------------------------------------------

_clients: dict[float, Any] = {}
_lock = threading.Lock()
CALL_LOG: list[dict] = []


def get_client(read_timeout: float):
    """Return a cached OpenAI-SDK client pointed at Gemini's endpoint."""
    key = settings.api_key()
    if not key:
        raise LLMError("MISSING_KEY", "GEMINI_API_KEY is missing.")

    with _lock:
        if read_timeout not in _clients:
            import httpx  # installed as a dependency of openai
            from openai import OpenAI

            _clients[read_timeout] = OpenAI(
                api_key=key,
                base_url=settings.GEMINI_OPENAI_BASE_URL,
                timeout=httpx.Timeout(
                    read_timeout,
                    connect=settings.CONNECT_TIMEOUT,
                ),
                max_retries=0,  # retries are handled here, with a policy
            )
        return _clients[read_timeout]


def reset_clients() -> None:
    with _lock:
        _clients.clear()


def usage_summary() -> dict:
    calls = len(CALL_LOG)
    ok = sum(1 for c in CALL_LOG if c.get("ok"))
    return {
        "requests": calls,
        "successful": ok,
        "failed": calls - ok,
        "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in CALL_LOG),
        "completion_tokens": sum(c.get("completion_tokens") or 0 for c in CALL_LOG),
        "seconds": round(sum(c.get("seconds") or 0 for c in CALL_LOG), 1),
    }


def _usage_numbers(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

MAX_TRANSIENT_RETRIES = 3
MAX_RATE_LIMIT_WAITS = 2
MAX_RATE_WAIT_SECONDS = 70.0
DEFAULT_RATE_WAIT_SECONDS = 30.0
TRANSIENT_BACKOFF_SECONDS = 3.0
_TRANSIENT = {"TIMEOUT", "CONNECTION", "SERVER"}

def chat(
    agent: str,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    tool_choice: Any = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
):
    """One chat-completion request with classified errors and bounded retries.

    Raises :class:`LLMError` - never a raw SDK exception.
    """
    read_timeout = settings.read_timeout_for(agent)
    params: dict[str, Any] = {
        "model": model or settings.model_for(agent),
        "messages": messages,
        "max_tokens": max_tokens or settings.max_tokens_for(agent),
        "reasoning_effort": reasoning_effort or settings.reasoning_effort_for(agent),
    }
    if tools:
        params["tools"] = tools
        params["tool_choice"] = tool_choice or "auto"

    transient_retries = 0
    rate_waits = 0

    while True:
        started = time.monotonic()
        try:
            client = get_client(read_timeout)
            response = client.chat.completions.create(**params)
        except Exception as exc:  # noqa: BLE001 - classified below
            err = classify_exception(exc)
            elapsed = time.monotonic() - started
            CALL_LOG.append({"agent": agent, "ok": False, "code": err.code,
                             "seconds": elapsed})
            print(f"[LLM] {agent}: {err.code} after {elapsed:.1f}s")

            if err.code in _TRANSIENT and transient_retries < MAX_TRANSIENT_RETRIES:
                transient_retries += 1
                wait = TRANSIENT_BACKOFF_SECONDS * (2 ** (transient_retries - 1))

                print(
                    f"[LLM] {agent}: retrying in {wait:.0f}s "
                    f"({transient_retries}/{MAX_TRANSIENT_RETRIES})"
                    )

                time.sleep(wait)
                continue
            
            if err.code == "RATE_LIMIT" and rate_waits < MAX_RATE_LIMIT_WAITS:
                wait = err.retry_after if err.retry_after is not None else DEFAULT_RATE_WAIT_SECONDS
                if wait <= MAX_RATE_WAIT_SECONDS:
                    rate_waits += 1
                    wait = max(wait, 1.0) + 1.0
                    print(f"[LLM] {agent}: rate limited, waiting {wait:.0f}s "
                          f"({rate_waits}/{MAX_RATE_LIMIT_WAITS})")
                    time.sleep(wait)
                    continue
                # The provider wants a long wait: treat as exhausted quota.
                err = LLMError(
                    "QUOTA",
                    f"Rate limit asks for a {wait:.0f}s wait; stopping instead of "
                    "blocking the workflow.",
                    status=err.status, detail=err.detail,
                )

            raise err from exc

        elapsed = time.monotonic() - started
        prompt_tokens, completion_tokens = _usage_numbers(response)
        finish = None
        try:
            finish = response.choices[0].finish_reason
        except (AttributeError, IndexError, TypeError):
            pass
        CALL_LOG.append({
            "agent": agent, "ok": True, "seconds": elapsed, "finish": finish,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        })
        print(f"[LLM] {agent}: {params['model']} {elapsed:.1f}s finish={finish} "
              f"tokens(in/out)={prompt_tokens}/{completion_tokens}")

        if not getattr(response, "choices", None):
            raise LLMError("MALFORMED", "The API response contained no choices.")
        return response


def chat_text(agent: str, system: str, user: str) -> str:
    """Plain text generation used by the Planner, Researcher and Developer.

    If the visible answer is empty or cut off, the usual cause on Gemini 3
    models is that thinking consumed the output budget; retry once with a
    larger budget instead of failing or accepting a half answer silently.
    """
    max_tokens = settings.max_tokens_for(agent)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    text = ""
    finish = None

    for attempt in range(2):
        response = chat(agent, messages, max_tokens=max_tokens)
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        finish = choice.finish_reason

        if text and finish != "length":
            return text
        if finish == "length" and attempt == 0:
            max_tokens = min(max_tokens * 2, settings.MAX_TOKENS_CEILING)
            print(f"[LLM] {agent}: output hit the token limit; retrying once with "
                  f"max_tokens={max_tokens}")
            continue
        break

    if not text:
        raise LLMError(
            "EMPTY" if finish != "length" else "TRUNCATED",
            f"The model returned no text (finish_reason={finish}).",
        )

    print(f"[LLM] {agent}: WARNING output still truncated at the token limit.")
    return text + "\n\n[NOTE: output truncated by the token limit]"
