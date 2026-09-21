from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.repositories.user_repository import UserRepository


async def authenticate_websocket(websocket: WebSocket,token: str,db: Session):
    payload=decode_token(token)

    if not payload:
        await websocket.close(code=1008)
        return None
    
    user_id=payload.get("sub")


    if not user_id:
        await websocket.close(code=1008)
        return None

    user_repository=UserRepository(db)

    user=user_repository.get_by_id(user_id)

    if not user:
        await websocket.close(code=1008)
        return None

    return user

