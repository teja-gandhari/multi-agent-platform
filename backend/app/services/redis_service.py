
from app.core.redis import redis_client

def publish_project_event(project_id: str ,message: str ):
    channel=f"project:{project_id}"

    return redis_client.publish(
        message=message,
        channel=channel
    )
