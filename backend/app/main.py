import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.auth import auth_router
from app.api.v1.projects import project_router
from app.api.v1.tasks import task_router
from app.websockets.project_ws import ws_router
from app.services.redis_subcriber import listen_for_project_events
from app.websockets.project_ws import ws_router,manager
from app.api.v1.agents import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Redis subscriber in the background
    subscriber_task = asyncio.create_task(
        listen_for_project_events(manager)
    )
    try:
        yield
    finally:
        # Stop subscriber when FastAPI shuts down
        subscriber_task.cancel()

        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)







app.include_router(health_router)
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(task_router)
app.include_router(ws_router,prefix="/ws")
app.include_router(router)


