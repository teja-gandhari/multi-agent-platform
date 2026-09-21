import asyncio
import json
import websockets

Token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmNTljY2Y5Yy00MGYzLTQ4MTQtOTQzMC03ZDY2NzE2MzBhNWUiLCJleHAiOjE3ODk5MDE5ODd9.4S_-4DxTEykp8zMQK5oqAhYAE3DfmxynNa_1StGdeT0"
async def receive_messages(websocket):
    try:
        while True:
            message = await websocket.recv()

            event = json.loads(message)

            print("\nProject:", event["project_id"])
            print("Agent:", event["agent"])
            print("Status:", event["status"])
            print("Message:", event["message"])

    except websockets.exceptions.ConnectionClosed:
        print("Connection closed")


async def send_messages(websocket):
    while True:
        message = await asyncio.to_thread(
            input,
            "Message: "
        )

        await websocket.send(message)


async def main():

    async with websockets.connect(
        f"ws://127.0.0.1:8000/ws/project-123?token={Token}"
    ) as websocket:

        print("Connected")

        receiver = asyncio.create_task(
            receive_messages(websocket)
        )

        sender = asyncio.create_task(
            send_messages(websocket)
        )

        await asyncio.gather(
            receiver,
            sender
        )


asyncio.run(main())
