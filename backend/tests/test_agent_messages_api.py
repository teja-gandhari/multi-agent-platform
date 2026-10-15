
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.agent_message import AgentMessage
from app.models.agent_run import AgentRun
from app.services.project_service import ProjectService


OWNER_ID = uuid4()
OTHER_USER_ID = uuid4()
PROJECT_ID = uuid4()
RUN_ID = uuid4()

NOW = datetime(2026, 10, 15, 10, 0, 0)


def messages_url(run_id=RUN_ID):
    """Get the actual registered URL from the OpenAPI schema."""
    paths = app.openapi()["paths"]

    for path in paths:
        if path.endswith("/agents/runs/{run_id}/messages"):
            return path.replace("{run_id}", str(run_id))

    raise AssertionError(
        "Agent messages endpoint is missing. Registered paths: "
        + ", ".join(paths.keys())
    )


def make_run():
    return SimpleNamespace(
        id=RUN_ID,
        project_id=PROJECT_ID,
        requested_task="Build a calculator",
        status="completed",
        result={"workflow_status": "completed"},
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_message(message_id, agent, status, message, created_at):
    return SimpleNamespace(
        id=message_id,
        run_id=RUN_ID,
        agent=agent,
        status=status,
        message=message,
        event_data={"source": "test"},
        created_at=created_at,
    )


class FakeQuery:
    def __init__(self, model, db):
        self.model = model
        self.db = db
        self.limit_value = None

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        self.limit_value = count
        return self

    def first(self):
        if self.model is AgentRun:
            return self.db.run
        return None

    def all(self):
        if self.model is AgentMessage:
            rows = self.db.messages
            if self.limit_value is not None:
                rows = rows[:self.limit_value]
            return rows
        return []


class FakeDB:
    def __init__(self):
        self.run = make_run()
        self.messages = [
            make_message(
                uuid4(),
                "planner",
                "completed",
                "Plan created",
                NOW,
            ),
            make_message(
                uuid4(),
                "researcher",
                "completed",
                "Research completed",
                NOW + timedelta(seconds=1),
            ),
            make_message(
                uuid4(),
                "tester",
                "completed",
                "Tests passed",
                NOW + timedelta(seconds=2),
            ),
        ]
        self.last_message_query = None

    def query(self, model):
        query = FakeQuery(model, self)
        if model is AgentMessage:
            self.last_message_query = query
        return query


@pytest.fixture
def messages_client(monkeypatch):
    fake_db = FakeDB()
    user = SimpleNamespace(id=OWNER_ID)

    def override_db():
        yield fake_db

    def check_project(self, project_id, current_user):
        if (
            project_id != PROJECT_ID
            or current_user.id != OWNER_ID
        ):
            raise HTTPException(
                status_code=404,
                detail="Project not found",
            )

        return SimpleNamespace(
            id=PROJECT_ID,
            owner_id=OWNER_ID,
        )

    monkeypatch.setattr(
        ProjectService,
        "get_project",
        check_project,
    )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        with TestClient(app) as client:
            yield client, fake_db, user
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_returns_messages_for_run(messages_client):
    client, _, _ = messages_client

    response = client.get(messages_url())

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3
    assert data[0]["run_id"] == str(RUN_ID)
    assert data[0]["agent"] == "planner"
    assert data[0]["message"] == "Plan created"
    assert data[1]["agent"] == "researcher"
    assert data[2]["agent"] == "tester"


def test_messages_are_limited_to_500(messages_client):
    client, fake_db, _ = messages_client

    response = client.get(messages_url())

    assert response.status_code == 200
    assert fake_db.last_message_query.limit_value == 500


def test_denies_user_who_does_not_own_project(messages_client):
    client, _, user = messages_client
    user.id = OTHER_USER_ID

    response = client.get(messages_url())

    assert response.status_code == 404


def test_unknown_run_returns_404(messages_client):
    client, fake_db, _ = messages_client
    fake_db.run = None

    response = client.get(messages_url())

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent run not found."
