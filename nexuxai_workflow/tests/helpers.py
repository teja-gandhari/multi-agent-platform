"""Fakes shared by the tests. No network, no API key, no quota."""
from __future__ import annotations

import json
from types import SimpleNamespace


def make_tool_call(call_id, name, args, signature=None, raw_arguments=None):
    function = SimpleNamespace(
        name=name,
        arguments=raw_arguments if raw_arguments is not None else json.dumps(args),
    )
    return SimpleNamespace(id=call_id, function=function, signature=signature)


def make_response(content=None, calls=(), finish=None):
    calls = list(calls)

    def model_dump(exclude_none=True):
        data = {"role": "assistant", "content": content, "annotations": [], "refusal": None}
        if calls:
            data["tool_calls"] = []
            for c in calls:
                entry = {
                    "id": c.id, "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                if c.signature:  # Gemini 3 thought signature
                    entry["extra_content"] = {"google": {"thought_signature": c.signature}}
                data["tool_calls"].append(entry)
        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}
        return data

    message = SimpleNamespace(content=content, tool_calls=calls or None, model_dump=model_dump)
    finish = finish or ("tool_calls" if calls else "stop")
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


class ScriptedChat:
    """Replacement for services.llm.chat that plays back a script."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []  # deep copies of the messages sent each round

    def __call__(self, agent, messages, **kwargs):
        self.requests.append(json.loads(json.dumps(messages)))
        if not self.script:
            raise AssertionError("model was called more times than scripted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeAPIError(Exception):
    """Mimics openai.APIStatusError (status_code + body)."""

    def __init__(self, status_code, body="", message="error"):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class APITimeoutError(Exception):  # same class name the openai SDK uses
    pass


class APIConnectionError(Exception):
    pass


GOOD_BACKEND = '''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/items/{item_id}")
def item(item_id: int):
    return {"id": item_id}
'''
GOOD_TEST = "from main import app\n\ndef test_ok():\n    assert app\n"
GOOD_REQS = "fastapi\nuvicorn\nhttpx\n"
GOOD_HTML = ('<html><head><link rel="stylesheet" href="style.css"></head>'
             '<body><script src="script.js"></script></body></html>')
GOOD_JS = ('const API_BASE = window.API_BASE || "http://127.0.0.1:8000";\n'
           'fetch(`${API_BASE}/items/${id}`);\nfetch(`${API_BASE}/health`);\n')
GOOD_CSS = "body { margin: 0; }\n"

GOOD_FILES = {
    "backend/main.py": GOOD_BACKEND,
    "backend/tests/test_main.py": GOOD_TEST,
    "backend/requirements.txt": GOOD_REQS,
    "frontend/index.html": GOOD_HTML,
    "frontend/script.js": GOOD_JS,
    "frontend/style.css": GOOD_CSS,
}
