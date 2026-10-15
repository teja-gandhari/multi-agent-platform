"""Central configuration for NexusAI.

* Loads ``.env`` from the project root exactly once.
* ``.env`` wins over stale OS-level environment variables (a leftover
  ``GEMINI_API_KEY`` or ``*_MODEL`` set in Windows would otherwise silently
  override the file you just edited).
* Never prints or returns secrets except through :func:`api_key`.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# utf-8-sig tolerates the BOM that some Windows editors add to .env files.
load_dotenv(ENV_PATH, override=True, encoding="utf-8-sig")

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-3.8-flash"

# Levels documented for gemini-3.8-flash: low, medium, high.
VALID_REASONING_EFFORTS = ("low", "medium", "high")
DEFAULT_REASONING_EFFORT = "low"

# max_tokens on Gemini 3 models INCLUDES thinking tokens, so budgets must be
# generous or the visible answer / tool-call arguments get truncated.
DEFAULT_MAX_TOKENS = {
    "planner": 8192,
    "researcher": 8192,
    "developer": 12288,
    "coder": 16384,
}
MAX_TOKENS_CEILING = 32768

CONNECT_TIMEOUT = 15.0
DEFAULT_READ_TIMEOUT = 120.0
CODER_READ_TIMEOUT = 180.0


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, "").strip())
        return value if value > 0 else default
    except ValueError:
        return default


def api_key() -> str | None:
    key = (os.getenv("GEMINI_API_KEY") or "").strip().strip("\"'").strip()
    return key or None


def model_for(agent: str) -> str:
    return (os.getenv(f"{agent.upper()}_MODEL") or "").strip() or DEFAULT_MODEL


def reasoning_effort_for(agent: str) -> str:
    raw = (
        os.getenv(f"{agent.upper()}_REASONING_EFFORT")
        or os.getenv("GEMINI_REASONING_EFFORT")
        or DEFAULT_REASONING_EFFORT
    )
    raw = raw.strip().lower()
    return raw if raw in VALID_REASONING_EFFORTS else DEFAULT_REASONING_EFFORT


def max_tokens_for(agent: str) -> int:
    return DEFAULT_MAX_TOKENS.get(agent, 8192)


def read_timeout_for(agent: str) -> float:
    default = CODER_READ_TIMEOUT if agent == "coder" else DEFAULT_READ_TIMEOUT
    return _float_env("LLM_TIMEOUT_SECONDS", default)


def describe() -> dict:
    """Non-secret summary used by the diagnostic script."""
    return {
        "env_file_found": ENV_PATH.is_file(),
        "api_key_set": api_key() is not None,
        "base_url": GEMINI_OPENAI_BASE_URL,
        "models": {a: model_for(a) for a in DEFAULT_MAX_TOKENS},
        "reasoning_effort": {a: reasoning_effort_for(a) for a in DEFAULT_MAX_TOKENS},
    }
