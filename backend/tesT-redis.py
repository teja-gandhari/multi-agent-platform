from app.services.redis_service import publish_project_event


result = publish_project_event(
    123,"hello"
)
print(result)