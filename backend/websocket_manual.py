
import asyncio
import json
import websockets

PROJECT_ID = input("Enter your project ID: ").strip()
TOKEN = input("Enter your JWT access token: ").strip()

URL = (
    f"ws://127.0.0.1:8000/ws/{PROJECT_ID}"
    f"?token={TOKEN}"
)


async def test_websocket():
    try:
        async with websockets.connect(URL) as websocket:
            print("Connected successfully!")

            message = await asyncio.wait_for(
                websocket.recv(),
                timeout=10
            )

            print("Received event:")
            print(json.dumps(json.loads(message), indent=4))

    except asyncio.TimeoutError:
        print("Connected, but no event received within 10 seconds.")
    except Exception as error:
        print(f"Error: {type(error).__name__}: {error}")

asyncio.run(test_websocket())
