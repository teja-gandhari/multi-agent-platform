from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
class ConnectionManager:
    def __init__(self):
        self.connection={}

    async def connect(self,project_id:str,websocket: WebSocket):
        await websocket.accept()

        if project_id not in self.connection:
            self.connection[project_id]=[]

        self.connection[project_id].append(websocket)

    def disconnect(self,project_id: str,websocket: WebSocket):
        if project_id not in self.connection:
            return
        if websocket in self.connection[project_id]:
            self.connection[project_id].remove(websocket)

        if not self.connection[project_id]:
            del self.connection[project_id]

    async def send_to_project(self,project_id: str, message: str):
      connection = self.connection.get(project_id,[])
      for websocket in connection.copy():
            try:
                await websocket.send_text(message)
            except WebSocketDisconnect:
                self.disconnect(project_id,websocket)
    

