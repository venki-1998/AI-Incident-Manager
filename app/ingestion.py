from kafka import KafkaProducer
import json
import time

producer = KafkaProducer(
    bootstrap_servers=["localhost:9092"],
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

logs = [
    {"service": "db", "message": "Connection timeout", "timestamp": time.time()},
    {"service": "api", "message": "503 Service Unavailable", "timestamp": time.time()},
]

for log in logs:
    producer.send("incidents", value=log)
    print(f"Sent: {log}")

producer.flush()