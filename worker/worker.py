import pika
import yaml
from model import model
from modules.browser import WorkerBrowser
from pika.adapters.blocking_connection import BlockingChannel


class Consumer:
    def __init__(self, config: model.Config) -> None:
        self.config: model.Config = config

    def consume(self) -> None:
        credentials = pika.PlainCredentials(username=self.config.rabbitmq.username, password=self.config.rabbitmq.password)
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.config.rabbitmq.host, credentials=credentials))
        channel: BlockingChannel = connection.channel()
        channel.queue_declare(queue=self.config.rabbitmq.url_queue)

        def _callback(ch: pika.channel.Channel, method: pika.spec.Basic.Deliver, properties: pika.spec.BasicProperties, body: bytes) -> None:
            browser = WorkerBrowser(config)
            url: str = body.decode(encoding="utf-8")
            browser.load(url)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=self.config.rabbitmq.url_queue, on_message_callback=_callback)

        print("Waiting for messages. To exit press CTRL+C")
        channel.start_consuming()


if __name__ == "__main__":
    # Load config
    with open("config/config.yaml", "r") as f_obj:
        config: model.Config = model.Config.from_dict(yaml.load(f_obj, Loader=yaml.SafeLoader))

    consumer = Consumer(config)
    consumer.consume()
