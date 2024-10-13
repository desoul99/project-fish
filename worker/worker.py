import asyncio
from aio_pika.abc import AbstractChannel, AbstractQueue, AbstractRobustConnection
import concurrent
from model import model
from modules.browser import WorkerBrowser
import aio_pika
import yaml


class Consumer:
    def __init__(self, config: model.Config) -> None:
        self.config: model.Config = config
        self.browser = WorkerBrowser(config)

    async def start_browser(self) -> None:
        await self.browser.start_browser()

    async def _on_message(self, message: aio_pika.IncomingMessage) -> None:
        url: str = message.body.decode()
        if not url.startswith("http"):
            url = "https://" + url
        await self.browser.main(url)
        await message.ack()

    async def main(self) -> None:
        connection: AbstractRobustConnection = await aio_pika.connect_robust(url=self.config.rabbitmq.get_connection_url(), no_ack=True)
        channel: AbstractChannel = await connection.channel()
        await channel.set_qos(prefetch_count=self.config.browser.max_tabs)
        queue: AbstractQueue = await channel.declare_queue(name=self.config.rabbitmq.url_queue, durable=False)
        await queue.consume(self._on_message)


if __name__ == "__main__":
    # Load config
    with open("config/config.yaml", "r") as f_obj:
        config: model.Config = yaml.load(f_obj, Loader=yaml.SafeLoader)

    consumer = Consumer(config)

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

    with concurrent.futures.ProcessPoolExecutor() as pool:
        # Run in a different process using run_in_executor
        loop.run_in_executor(pool, consumer.start_browser())

    loop.create_task(consumer.main())
    loop.run_forever()
