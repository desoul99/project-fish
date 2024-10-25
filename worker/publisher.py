#!/usr/bin/env python
import json
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

message = {}

if len(sys.argv[1:]) == 1:
    message = {"url": sys.argv[1], "emulation_device": "pixel7", "proxy": "https://test.com"}


channel.basic_publish(exchange="", routing_key="pf_urlqueue", body=json.dumps(message))

print(f" [x] Sent {message}")

connection.close()
