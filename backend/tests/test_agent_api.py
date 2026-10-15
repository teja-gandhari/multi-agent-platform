
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_agent_run_rejects_missing_authentication():
    response = client.post(
        "/agents/run",
        json={
            "project_id": "00000000-0000-0000-0000-000000000001",
            "task": "Build a simple task management application",
        },
    )

    assert response.status_code in (401, 403)


def test_agent_run_rejects_invalid_project_id():
    response = client.post(
        "/agents/run",
        headers={"Authorization": "Bearer invalid-token"},
        json={
            "project_id": "not-a-valid-uuid",
            "task": "Build a simple application",
        },
    )

    assert response.status_code in (401, 403, 422)
