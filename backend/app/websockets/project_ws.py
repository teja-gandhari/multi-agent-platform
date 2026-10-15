
from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect
import asyncio

from app.schemas.websocket_events import AgentEvent
from app.models.enums import AgentStatus, AgentType
from app.core.websocket_auth import authenticate_websocket
from app.database.session import get_db
from app.repositories.project_repository import ProjectRepository
from app.websockets.connection_manager import ConnectionManager
from app.services.redis_service import publish_project_event


ws_router = APIRouter()
manager = ConnectionManager()


@ws_router.websocket("/{project_id}")
async def msg(
    project_id: str,
    token: str,
    websocket: WebSocket,
    db: Session = Depends(get_db),
):
    try:
        # Step 1: Authenticate the user
        user = await authenticate_websocket(websocket, token, db)

        if not user:
            return

        # Step 2: Verify project ownership
        project_repository = ProjectRepository(db)
        project = project_repository.get_by_id(project_id)

        if not project or project.owner_id != user.id:
            await websocket.close(code=1008)
            return

        # Step 3: Connect the WebSocket client
        await manager.connect(project_id, websocket)


        # Step 4: Keep the connection alive
        while True:
            await asyncio.sleep(60)

    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
