"""Staged diagnostics for the Gemini connection NexusAI uses.

Run from the project root (venv active):

    python diagnose_llm.py            # stages 1-5 (uses ~3 generation requests)
    python diagnose_llm.py --native   # also test Google's native SDK (+1 request)

Each stage prints PASS / FAIL with a classified reason. The key is never
printed. Stop reading at the first FAIL: later stages depend on it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from config import settings
from services import llm
from services.llm import LLMError, classify_exception, explain

AGENT = "coder"  # same timeout/token/effort settings the real Coder uses


def stage(title: str) -> None:
    print(f"\n=== {title}")


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def stage_env() -> bool:
    stage("1. Environment (no network)")
    info = settings.describe()
    print(f"  .env file found : {info['env_file_found']}")
    print(f"  GEMINI_API_KEY  : {'set' if info['api_key_set'] else 'MISSING'}")
    print(f"  base URL        : {info['base_url']}")
    print(f"  models          : {info['models']}")
    print(f"  reasoning effort: {info['reasoning_effort']}")
    proxies = [n for n in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
                           "https_proxy", "all_proxy") if os.getenv(n)]
    print(f"  proxy variables : {proxies or 'none set'}")
    if proxies:
        print("  NOTE  a proxy is configured; a slow/blocked proxy causes timeouts.")
    if not info["api_key_set"]:
        fail("GEMINI_API_KEY missing")
        return False
    ok("configuration loaded")
    return True


def stage_model_lookup() -> bool:
    stage("2. Model lookup on the OpenAI-compatible endpoint (free metadata call)")
    model = settings.model_for(AGENT)
    started = time.monotonic()
    try:
        llm.get_client(30).models.retrieve(model)
    except Exception as exc:  # noqa: BLE001
        err = classify_exception(exc)
        fail(f"{explain(err)}  ({time.monotonic() - started:.1f}s)")
        return False
    ok(f"'{model}' is visible to this key ({time.monotonic() - started:.1f}s)")
    return True


def stage_basic_chat() -> bool:
    stage("3. Basic chat completion (1 request)")
    started = time.monotonic()
    try:
        response = llm.chat(
            AGENT,
            [{"role": "user", "content": "Reply with exactly: NEXUS_OK"}],
            max_tokens=1024,
        )
    except LLMError as err:
        fail(explain(err))
        return False
    choice = response.choices[0]
    text = (choice.message.content or "").strip()
    usage = getattr(response, "usage", None)
    print(f"  reply={text!r} finish={choice.finish_reason} "
          f"tokens(in/out)={getattr(usage, 'prompt_tokens', '?')}/"
          f"{getattr(usage, 'completion_tokens', '?')} "
          f"({time.monotonic() - started:.1f}s)")
    if not text:
        fail("empty reply (thinking may have consumed the budget)")
        return False
    ok("chat works on the compatibility endpoint")
    return True


TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write a file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
}


def stage_tool_roundtrip() -> bool:
    stage("4. Tool-calling round trip, exactly as the Coder does it (2 requests)")
    from agents.coder import assistant_record  # reuse the real serializer

    messages = [{
        "role": "user",
        "content": "Call write_file with path 'hello.txt' and content 'hi'. Then say DONE.",
    }]
    try:
        first = llm.chat(AGENT, messages, tools=[TOOL], max_tokens=2048)
    except LLMError as err:
        fail("request 1: " + explain(err))
        return False

    message = first.choices[0].message
    calls = list(message.tool_calls or [])
    if not calls:
        fail(f"model returned no tool call (content={message.content!r}, "
             f"finish={first.choices[0].finish_reason})")
        return False

    call = calls[0]
    try:
        args = json.loads(call.function.arguments)
        assert isinstance(args, dict) and "path" in args
    except Exception as exc:  # noqa: BLE001
        fail(f"tool arguments not parseable: {exc}: {call.function.arguments!r}")
        return False
    ok(f"tool call parsed: {call.function.name}({sorted(args)})  id={call.id!r}")

    record = assistant_record(message)
    has_sig = any("extra_content" in tc for tc in record.get("tool_calls", []))
    print(f"  thought-signature field present on tool call: {has_sig}")

    messages.append(record)
    messages.append({
        "role": "tool", "tool_call_id": call.id, "name": call.function.name,
        "content": json.dumps({"ok": True, "path": args.get("path")}),
    })
    try:
        second = llm.chat(AGENT, messages, tools=[TOOL], max_tokens=2048)
    except LLMError as err:
        fail("request 2 (sending the tool result back) was rejected: " + explain(err))
        print("  -> This is the multi-turn tool format. Report this exact message.")
        return False
    ok(f"tool result accepted; model replied: "
       f"{(second.choices[0].message.content or '').strip()[:60]!r}")
    return True


def stage_native() -> bool:
    stage("5. Native Google SDK (comparison only; 1 request)")
    try:
        from google import genai
    except ImportError:
        fail("google-genai not installed (pip install google-genai)")
        return False
    started = time.monotonic()
    try:
        client = genai.Client(api_key=settings.api_key())
        reply = client.models.generate_content(
            model=settings.model_for(AGENT), contents="Reply with exactly: NATIVE_OK"
        )
        ok(f"native SDK reply {reply.text!r} ({time.monotonic() - started:.1f}s)")
        return True
    except Exception as exc:  # noqa: BLE001
        fail(f"{type(exc).__name__}: {llm._redact(str(exc))[:300]}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()

    results = {}
    for name, fn in (("environment", stage_env), ("model lookup", stage_model_lookup),
                     ("basic chat", stage_basic_chat), ("tool round trip", stage_tool_roundtrip)):
        results[name] = fn()
        if not results[name]:
            break
    if args.native:
        results["native sdk"] = stage_native()

    print("\n=== Summary")
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    print(f"  LLM requests used: {llm.usage_summary()['requests']}")
    return 0 if all(results.values()) and len(results) >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
