from fastapi import APIRouter, WebSocket,Depends
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect
import asyncio

from app.websockets.connection_manager import ConnectionManager
from app.schemas.websocket_events import AgentEvent
from app.models.enums import AgentStatus,AgentType
from app.core.websocket_auth import authenticate_websocket
from app.database.session import get_db
from app.repositories.project_repository import ProjectRepository


ws_router = APIRouter()

manager=ConnectionManager()

@ws_router.websocket("/{project_id}")
async def msg(project_id: str,token: str,websocket: WebSocket,db:Session=Depends(get_db)):

        #project is id str look over this
        


    try:
        user = await authenticate_websocket(websocket,token,db)

        if not user:
            return 

        project_repository=ProjectRepository(db)

        project=project_repository.get_by_id(project_id)

        if not project or project.owner_id != user.id:
            await websocket.close(code=1008)
            return 


        await manager.connect(project_id,websocket)

        event=AgentEvent(
            project_id=project_id,
            agent=AgentType.PLANNER,
            status=AgentStatus.IN_PROGRESS,
            message="Planner started"
        )
      
        # message = await websocket.receive_text()
        await manager.send_to_project(
            project_id,
            event.model_dump_json()
        )
        while True:
            await asyncio.sleep(60)
            

    except WebSocketDisconnect:
        manager.disconnect(project_id,websocket)