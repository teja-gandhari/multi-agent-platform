
import asyncio
import logging

from app.core.redis import redis_client

logger = logging.getLogger(__name__)


async def listen_for_project_events(manager):
    pubsub = redis_client.pubsub()

    await asyncio.to_thread(
        pubsub.psubscribe,
        "project:*"
    )

    logger.info("Redis subscriber started")
    print("Redis SUbcriber Started broo",flush=True)

    try:
        while True:
            message = await asyncio.to_thread(
                pubsub.get_message,
                ignore_subscribe_messages=True,
                timeout=1.0
            )

            if message and message["type"] == "pmessage":
                project_id = message["channel"].removeprefix("project:")
                event_json = message["data"]

                await manager.send_to_project(
                    project_id,
                    event_json
                )

            await asyncio.sleep(0.01)

    finally:
        await asyncio.to_thread(pubsub.close)
