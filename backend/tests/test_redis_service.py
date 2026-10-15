
from unittest.mock import patch

from app.services.redis_service import publish_project_event


def test_publish_project_event_uses_project_channel():
    project_id = "project-123"
    message = '{"agent":"planner","status":"in_progress"}'

    with patch(
        "app.services.redis_service.redis_client.publish",
        return_value=1,
    ) as mock_publish:
        result = publish_project_event(project_id, message)

    mock_publish.assert_called_once_with(
        message=message,
        channel=f"project:{project_id}",
    )
    assert result == 1
