
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_project_list_requires_authentication():
    response = client.get("/project")

    assert response.status_code in (401, 403)


def test_project_creation_requires_authentication():
    response = client.post(
        "/project",
        json={
            "title": "Security Test Project",
            "description": "Testing authentication",
        },
    )

    assert response.status_code in (401, 403)


def test_agent_run_requires_authentication():
    response = client.post(
        "/agents/run",
        json={
            "project_id": "00000000-0000-0000-0000-000000000001",
            "task": "Build a simple test application",
        },
    )

    assert response.status_code in (401, 403)
