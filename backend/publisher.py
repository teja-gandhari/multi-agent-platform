import redis

redis_client=redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)


messages=redis_client.publish("project:123","Planneer Started")

print("Message sent")