import asyncio
from unittest.mock import AsyncMock

from app.websockets.connection_manager import ConnectionManager


def test_connect_and_disconnect():
    async def run_test():
        manager = ConnectionManager()
        websocket = AsyncMock()

        await manager.connect("project-123", websocket)

        def is_connected():
            return any(
                isinstance(value, dict)
                and websocket in value.get("project-123", [])
                for value in vars(manager).values()
            )

        assert is_connected(), "WebSocket was not registered"

        manager.disconnect("project-123", websocket)

        assert not is_connected(), "WebSocket was not removed"

    asyncio.run(run_test())


def test_send_to_project():
    async def run_test():
        manager = ConnectionManager()
        websocket = AsyncMock()

        await manager.connect("project-123", websocket)
        await manager.send_to_project(
            "project-123",
            '{"status":"in_progress"}',
        )

        websocket.send_text.assert_awaited_once_with(
            '{"status":"in_progress"}'
        )

    asyncio.run(run_test())
