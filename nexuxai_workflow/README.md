# NexusAI — multi-agent application generator

Describe an app in plain English; seven agents plan, research, specify, code,
test, review and launch it locally.

```
Planner → Researcher → Developer → Coder → Tester → Reviewer → Runner → URL
                                     ▲         │         │
                                     └─ repair ┴─────────┘   (max 3 Coder attempts)
```

| Agent | Uses LLM | Job |
|---|---|---|
| Planner / Researcher / Developer | yes | plan → research brief → implementation spec |
| Coder | yes (tool calling) | writes files via a `write_file` tool; gets the spec + failure details |
| Tester | no | required files, syntax, dependency policy, frontend↔backend contract, isolated venv, `pip install`, `pytest`, live `/health` |
| Reviewer | no | approves only if generation completed and every Tester check ran and passed |
| Runner | no | starts backend (:8000) and frontend (:8080), returns the URL only after both respond |

## Setup (Windows)

```
cd "D:\Nexux AI\ai_module"
venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env      (then add your key; free key: https://aistudio.google.com/apikey)
python diagnose_llm.py      (checks key, model, chat and tool calling)
python main.py "build a weather application"
```

Ctrl+C stops the generated app. `python main.py --detach "..."` leaves it
running; `python main.py --stop` stops it.

## Free-tier notes

One run is roughly 3 text requests plus ~3–10 Coder requests (more per repair
attempt). Per-minute limits are waited out automatically; daily quota
exhaustion stops the run with an explanation. Your exact limits are shown in
Google AI Studio. Thinking tokens count toward limits, so the default is
`reasoning_effort=low`.

## Tests (no network, no API quota)

```
python -m pytest
```

## Contract for generated apps

Backend `uvicorn main:app` on 8000 with CORS enabled; frontend static on 8080
calling `${API_BASE}/path` (default `http://127.0.0.1:8000`); dependencies
limited to FastAPI-stack packages (no Redis/Postgres); tests never use the
network. The Tester enforces this.
