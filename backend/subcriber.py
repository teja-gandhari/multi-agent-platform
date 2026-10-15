import redis

redis_client = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)

print("Redis connection:", redis_client.ping())

pubsub = redis_client.pubsub()

pubsub.subscribe("project:123")

print("Subscribed to project:123")
print("Channels:", pubsub.channels)

for message in pubsub.listen():
    if message["type"]=="message":
        print(message)
