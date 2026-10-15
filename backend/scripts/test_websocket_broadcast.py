
import asyncio
import json
import os
from urllib.parse import urlencode

import redis
import websockets


PROJECT_ID = os.environ.get("PROJECT_ID")
JWT_TOKEN = os.environ.get("JWT_TOKEN")

BASE_URL = os.environ.get(
    "WEBSOCKET_BASE_URL",
    "ws://127.0.0.1:8000",
)
REDIS_URL = os.environ.get(
    "REDIS_URL",
    "redis://localhost:6379/0",
)


async def main():
    if not PROJECT_ID or not JWT_TOKEN:
        raise RuntimeError(
            "Set PROJECT_ID and JWT_TOKEN environment variables first."
        )

    query = urlencode({"token": JWT_TOKEN})
    url = f"{BASE_URL}/ws/{PROJECT_ID}?{query}"
    channel = f"project:{PROJECT_ID}"

    redis_client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
    )

    ws1 = None
    ws2 = None

    try:
        # Connect two independent clients to the same project.
        ws1 = await websockets.connect(url)
        print("Client A connected.")

        ws2 = await websockets.connect(url)
        print("Client B connected.")

        # Publish a test event through Redis.
        event = {
            "project_id": PROJECT_ID,
            "agent": "tester",
            "status": "completed",
            "message": "Redis broadcast integration test",
        }

        # Allow the subscriber to finish processing subscriptions.
        await asyncio.sleep(0.5)

        subscriber_count = await asyncio.to_thread(
            redis_client.publish,
            channel,
            json.dumps(event),
        )

        print(f"Redis publish returned: {subscriber_count}")

        # Both clients must receive the same event.
        received_a, received_b = await asyncio.wait_for(
            asyncio.gather(
                ws1.recv(),
                ws2.recv(),
            ),
            timeout=10,
        )

        data_a = json.loads(received_a)
        data_b = json.loads(received_b)

        assert data_a["project_id"] == PROJECT_ID
        assert data_b["project_id"] == PROJECT_ID
        assert data_a["message"] == event["message"]
        assert data_b["message"] == event["message"]

        print("\nPASS: Client A received the event.")
        print("PASS: Client B received the event.")
        print("PASS: Both clients received the same project event.")
        print("\nReceived event:")
        print(json.dumps(data_a, indent=2))

    finally:
        if ws1 is not None:
            await ws1.close()

        if ws2 is not None:
            await ws2.close()

        await asyncio.to_thread(redis_client.close)


if __name__ == "__main__":
    asyncio.run(main())
