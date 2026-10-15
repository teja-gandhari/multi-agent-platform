
import asyncio
import json
import os

import websockets


TOKEN = os.environ["WS_TOKEN"]
PROJECT_ID = os.environ["WS_PROJECT_ID"]

WS_URL = (
    f"ws://127.0.0.1:8000/ws/{PROJECT_ID}"
    f"?token={TOKEN}"
)


async def main():
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("Connected. Waiting for agent events...")

            async for message in websocket:
                try:
                    event = json.loads(message)

                    print(f"\nProject: {event['project_id']}")
                    print(f"Agent:   {event['agent']}")
                    print(f"Status:  {event['status']}")
                    print(f"Message: {event['message']}")

                except (json.JSONDecodeError, KeyError):
                    print(f"\nReceived: {message}")

    except websockets.exceptions.ConnectionClosed as exc:
        print(f"Connection closed: {exc.code}")

    finally:
        print("WebSocket test stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
