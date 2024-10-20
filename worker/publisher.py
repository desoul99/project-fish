#!/usr/bin/env python
import pika
import sys
import yaml

# Load config
with open("config/config.yaml", "r") as f_obj:
    config = yaml.load(f_obj, Loader=yaml.SafeLoader)

credentials = pika.PlainCredentials(username=config["rabbitmq"]["username"], password=config["rabbitmq"]["password"])
connection = pika.BlockingConnection(pika.ConnectionParameters("localhost", credentials=credentials))
channel = connection.channel()

channel.queue_declare(queue="pf_urlqueue")

message = " ".join(sys.argv[1:]) or "https://google.com"

channel.basic_publish(exchange="", routing_key="pf_urlqueue", body=message)

print(f" [x] Sent {message}")

connection.close()
