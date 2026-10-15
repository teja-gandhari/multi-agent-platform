
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.agent_run import AgentRun
from app.services.project_service import ProjectService


OWNER_ID = uuid4()
OTHER_USER_ID = uuid4()
PROJECT_ID = uuid4()
RUN_ID = uuid4()
NOW = datetime(2026, 10, 15, 10, 0, 0)


def history_url(project_id=PROJECT_ID):
    """Discover the registered history endpoint using OpenAPI."""
    paths = app.openapi()["paths"]

    for path in paths:
        if path.endswith("/agents/runs/{project_id}"):
            return path.replace("{project_id}", str(project_id))

    raise AssertionError(
        "History endpoint is missing from OpenAPI paths: "
        + ", ".join(paths.keys())
    )


def make_run(run_id=RUN_ID, project_id=PROJECT_ID):
    return SimpleNamespace(
        id=run_id,
        project_id=project_id,
        requested_task="Build and test a calculator",
        status="completed",
        result={"workflow_status": "completed"},
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.limit_value = None

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        self.limit_value = count
        return self

    def all(self):
        return self.rows[:self.limit_value]


class FakeDB:
    def __init__(self, rows):
        self.query_result = FakeQuery(rows)

    def query(self, model):
        assert model is AgentRun
        return self.query_result


@pytest.fixture
def history_client(monkeypatch):
    fake_db = FakeDB([make_run()])
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


def test_history_returns_saved_run(history_client):
    client, _, _ = history_client

    response = client.get(history_url())

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(RUN_ID)
    assert data[0]["project_id"] == str(PROJECT_ID)
    assert data[0]["requested_task"] == (
        "Build and test a calculator"
    )
    assert data[0]["status"] == "completed"


def test_history_limits_results_to_50(history_client):
    client, fake_db, _ = history_client

    response = client.get(history_url())

    assert response.status_code == 200
    assert fake_db.query_result.limit_value == 50


def test_history_denies_other_user(history_client):
    client, _, user = history_client
    user.id = OTHER_USER_ID

    response = client.get(history_url())

    assert response.status_code == 404


def test_history_denies_unknown_project(history_client):
    client, _, _ = history_client

    response = client.get(history_url(uuid4()))

    assert response.status_code == 404
