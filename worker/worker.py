from modules.browser import Browser
import asyncio
import aio_pika
import yaml


class Consumer():
    def __init__(self, config):
        self.config = config
        self.amqp_url = f"amqp://{self.config['rabbitmq']['username']}:{self.config['rabbitmq']['password']}@localhost/"
        self.browser = Browser(config)

    async def start_browser(self):
        await self.browser.start_browser()

    async def on_message(self, message: aio_pika.IncomingMessage):
        url = message.body.decode()
        if not url.startswith('http'):
            url = 'https://' + url
        await self.browser.main(url)
        await message.ack()

    async def main(self):
        connection = await aio_pika.connect_robust(self.amqp_url, no_ack=True)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=self.config['browser']['max_tabs'])
    
        queue_name = self.config['rabbitmq']['queue']
        queue = await channel.declare_queue(queue_name, durable=False)
    
        await queue.consume(self.on_message)


if __name__ == "__main__":
    # Load config
    with open('config/config.yaml', 'r') as f_obj:
        config = yaml.load(f_obj, Loader=yaml.SafeLoader)

    consumer = Consumer(config)
    loop = asyncio.new_event_loop()

    loop.run_until_complete(consumer.start_browser())

    loop.create_task(consumer.main())
    loop.run_forever()
