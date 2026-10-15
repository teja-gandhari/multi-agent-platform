# NexusAI --- Cloud-Native Multi-Agent Collaboration Platform

> A prototype platform for coordinating specialized AI agents through a
> reviewable workflow, with a FastAPI backend, LangGraph orchestration,
> PostgreSQL persistence, Redis Pub/Sub, and WebSocket progress events.

**Repository:** https://github.com/teja-gandhari/multi-agent-platform

## Overview

NexusAI lets a user submit a task to a multi-agent workflow. The Planner
creates an implementation plan, the user reviews it and can request
changes, and downstream agents continue after approval. The backend
manages authentication, projects, tasks, workflow runs, and agent
messages.

> **Status:** College/resume prototype. Backend tests and several
> integration checks have passed in the development environment. Verify
> the full workflow and frontend integration in your own environment
> before describing them as production-ready.

## Features

-   JWT authentication and password hashing.
-   Project and task REST APIs, pagination, and status lifecycle
    handling.
-   Ownership and authorization checks for protected resources.
-   LangGraph workflow with Planner, Researcher, Developer, Coder,
    Tester, Reviewer, and Runner agents.
-   Planner approval and plan-revision flow.
-   PostgreSQL persistence for application data, workflow runs, and
    agent messages.
-   Redis Pub/Sub and WebSockets for real-time progress events.
-   SQLAlchemy models and Alembic migrations.
-   Automated tests with pytest.

## Architecture

``` mermaid
flowchart TD
    U[Frontend / User] -->|REST + JWT| API[FastAPI Backend]
    U <-->|Progress events| WS[WebSocket Router]
    API --> DB[(PostgreSQL)]
    API --> ADAPTER[Workflow Adapter]
    ADAPTER --> LG[LangGraph Workflow]
    LG --> P[Planner]
    P --> G{Plan approved?}
    G -->|Request changes| P
    G -->|Approved| R[Researcher]
    R --> D[Developer]
    D --> C[Coder]
    C --> T[Tester]
    T --> V[Reviewer]
    V --> X[Runner]
    ADAPTER <--> REDIS[(Redis Pub/Sub)]
    REDIS --> WS
    ADAPTER --> DB
```

## Technology Stack

  Area                   Technologies
  ---------------------- ---------------------------------------
  Backend                Python, FastAPI
  Data                   PostgreSQL, SQLAlchemy, Alembic
  Authentication         JWT, password hashing
  AI orchestration       LangGraph and configured LLM provider
  Real-time              WebSockets, Redis Pub/Sub
  Testing                pytest
  Local infrastructure   Docker where configured

## Repository Structure

``` text
multi-agent-platform/
├── backend/
│   ├── app/                 # API, models, schemas, services, repositories
│   ├── alembic/             # Database migrations
│   ├── tests/               # Automated tests
│   └── requirements.txt     # If present in the repository
├── nexuxai_workflow/
│   ├── agents/              # Specialized agent implementations
│   ├── workflow.py          # LangGraph state and graph
│   └── main.py              # Workflow entry points
├── .env.example             # Sanitized configuration template
├── .gitignore
└── README.md
```

The current workflow directory is spelled `nexuxai_workflow`. Preserve
this spelling unless you update the adapter path and imports as well.

## Getting Started

### Prerequisites

-   Git and Python compatible with the dependency files.
-   PostgreSQL and Redis.
-   An LLM provider API key if your configured agents use an external
    model.
-   Docker is optional if you run services locally without containers.

### 1. Clone

``` bash
git clone https://github.com/teja-gandhari/multi-agent-platform.git
cd multi-agent-platform
```

### 2. Configure environment

Create a local `.env` file based on `.env.example` and fill in the
variable names required by the application. These commonly include
database connection settings, JWT settings, Redis configuration, and
model-provider credentials. Use the actual configuration expected by the
code.

**Never commit `.env` files, real API keys, JWT secrets, passwords, or
database credentials.**

### 3. Set up the backend (Windows PowerShell)

``` powershell
cd backend
python -m venv venv
.env\Scripts\Activate.ps1
```

Install dependencies using the dependency file present in the
repository. If `requirements.txt` exists:

``` powershell
python -m pip install -r requirements.txt
```

### 4. Prepare PostgreSQL

Start PostgreSQL, create/configure the database, and run Alembic from
the directory containing the project's `alembic.ini`:

``` powershell
alembic upgrade head
```

If the Alembic configuration is located elsewhere, run the command from
that configured directory.

### 5. Start Redis

If Redis is not already running and Docker is installed:

``` bash
docker run --name nexusai-redis -p 6379:6379 -d redis:7
```

If a container with that name already exists, start or reuse it rather
than creating a duplicate.

### 6. Start FastAPI

From `backend/`, with the virtual environment activated:

``` powershell
uvicorn app.main:app --reload
```

-   Swagger API docs: http://127.0.0.1:8000/docs
-   Health endpoint, if enabled: http://127.0.0.1:8000/health

### 7. Run tests

From the backend environment:

``` powershell
python -m pytest -q
```

A passing test suite confirms the tests in that environment passed; it
does not guarantee every deployment or frontend scenario works.

## API Overview

Confirm exact route prefixes and request schemas in Swagger (`/docs`).

  ----------------------------------------------------------------------------------------------
  Capability              Endpoint                                       Purpose
  ----------------------- ---------------------------------------------- -----------------------
  Health                  `GET /health`                                  Service health check

  Authentication          `/auth/...`                                    Authentication and
                                                                         token flow

  Projects                `/projects/...`                                Project management

  Tasks                   `/tasks/...`                                   Task management

  Start AI run            `POST /agents/run`                             Start a workflow for a
                                                                         project

  Run history             `GET /agents/runs/{project_id}`                List runs for a project

  Get plan                `GET /agents/runs/{run_id}/plan`               Retrieve plan and
                                                                         approval state

  Approve plan            `POST /agents/runs/{run_id}/approve`           Approve a pending plan

  Request changes         `POST /agents/runs/{run_id}/request-changes`   Ask Planner to revise a
                                                                         pending plan

  Run messages            `GET /agents/runs/{run_id}/messages`           Retrieve messages for a
                                                                         run

  WebSocket               `WS /ws/{project_id}?token=...`                Receive project-scoped
                                                                         progress events
  ----------------------------------------------------------------------------------------------

Protected routes require the authentication configured by the backend.
Use the exact schemas shown in Swagger.

## Workflow

1.  User creates a project and submits a task.
2.  FastAPI starts the LangGraph workflow.
3.  Planner generates a plan.
4.  Workflow pauses for user approval.
5.  User requests revisions or approves the plan.
6.  After approval, downstream agents execute according to the graph's
    routing logic.
7.  Run history and agent messages are saved.
8.  Progress events can be distributed through Redis and delivered over
    WebSockets.

### Approval behavior and checkpoint limitation

-   Request changes while the run is awaiting approval.
-   Approve the plan after reviewing the revised version.
-   Requesting changes after approval may return `409 Conflict` because
    the run is no longer waiting for approval.
-   The current prototype uses an **in-memory LangGraph checkpointer**.
    Pending approval state can be lost if the backend process restarts.
    Persistent checkpoint storage is recommended for restart-safe use.

## End-to-End Test Checklist

-   [ ] Authenticate and create a project.
-   [ ] Start a run and confirm the plan is returned.
-   [ ] Confirm the workflow waits for approval.
-   [ ] Request changes and verify the plan incorporates feedback.
-   [ ] Approve the revised plan and verify downstream execution.
-   [ ] Retrieve run history and agent messages from the API.
-   [ ] Verify another user cannot access unauthorized project/run data.
-   [ ] Confirm connected WebSocket clients receive progress events.
-   [ ] Run `python -m pytest -q`.
-   [ ] Test frontend integration separately once the UI is connected.


## 👥 Contributors

This project is developed collaboratively, with each contributor responsible for different components of the platform.

| GitHub Account | Responsibility | Contributions |
|---|---|---|
| [@teja-gandhari](https://github.com/teja-gandhari) | Backend & Integration | FastAPI, PostgreSQL, SQLAlchemy, Alembic, JWT authentication, project/task APIs, Redis Pub/Sub, WebSockets, run history, and backend–AI workflow integration. |
| [@maheshguggilla2504-oss](https://github.com/maheshguggilla2504-oss) | AI & LangGraph | Multi-agent orchestration, LangGraph workflow, agent coordination, planning, and workflow execution. |
| Frontend Contributor | Frontend Development | UI development, API integration, Planner approval screens, live agent progress, and run history interface. |

### Related Repositories

- **Main Platform:** [multi-agent-platform] (https://github.com/teja-gandhari/multi-agent-platform)
- **Frontend:** [nexuxai_frontend] (https://github.com/maheshguggilla2504-oss/nexus-ai-orchestrator)

We collaborate to integrate the backend, AI orchestration, and frontend into one multi-agent platform.

## Security

-   Keep secrets in environment variables or a secrets manager.
-   Commit only a sanitized `.env.example`.
-   If a secret was committed, revoke or rotate it; deleting it in a
    later commit does not remove it from Git history.
-   Keep authorization checks enabled for protected endpoints.
-   Do not expose development credentials or database ports publicly.

## Limitations and Future Work

-   Use persistent LangGraph checkpoint storage for restart-safe
    approvals.
-   Complete and test the frontend integration.
-   Add structured logs, metrics, and tracing for workflow runs.
-   Improve retries, timeouts, and recovery from agent failures.
-   Add CI checks and deployment configuration.
-   Review rate limiting and production security before public
    deployment.

## Contributing

1.  Create a branch for your change.
2.  Make focused changes and add/update tests.
3.  Run relevant tests locally.
4.  Open a pull request against `main` with a clear description.

