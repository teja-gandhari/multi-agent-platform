
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.project_service import ProjectService


def test_project_owner_can_access_project():
    project_id = uuid4()
    owner = MagicMock()
    owner.id = uuid4()

    project = MagicMock()
    project.id = project_id
    project.owner_id = owner.id

    service = ProjectService.__new__(ProjectService)
    service.project_repository = MagicMock()
    service.project_repository.get_by_id.return_value = project

    result = service.get_project(project_id, owner)

    assert result == project


def test_non_owner_cannot_access_project():
    project_id = uuid4()

    owner = MagicMock()
    owner.id = uuid4()

    another_user = MagicMock()
    another_user.id = uuid4()

    project = MagicMock()
    project.id = project_id
    project.owner_id = owner.id

    service = ProjectService.__new__(ProjectService)
    service.project_repository = MagicMock()
    service.project_repository.get_by_id.return_value = project

    with pytest.raises(HTTPException) as exc:
        service.get_project(project_id, another_user)

    assert exc.value.status_code == 403
