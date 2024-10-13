import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import Executor, ProcessPoolExecutor

import aio_pika
import yaml
from aio_pika.abc import AbstractChannel, AbstractQueue, AbstractRobustConnection
from model import model
from modules.browser import WorkerBrowser

logging.basicConfig(level=logging.WARNING)


# Debugging purposes
class MonitoringProcessPoolExecutor(ProcessPoolExecutor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _adjust_process_count(self):
        super()._adjust_process_count()  # Call the base class method
        print(f"Current active processes: {len(self._processes)}")

    def submit(self, fn, *args, **kwargs):
        print(f"Submitting task {fn.__name__} with args: {args}")
        return super().submit(fn, *args, **kwargs)

    def _process_terminate(self, process):
        print(f"Process {process.pid} terminated.")
        super()._process_terminate(process)


def process_message(url: str, config: model.Config) -> None:
    print(f"Process {multiprocessing.current_process().pid} started.")
    start_time: float = time.time()

    browser = WorkerBrowser(config)
    browser.loop.run_until_complete(browser.load(url))

    end_time: float = time.time()
    elapsed_time: float = end_time - start_time
    print(f"Process {multiprocessing.current_process().pid} finished execution in {elapsed_time:.6f} seconds.")


class Consumer:
    def __init__(self, config: model.Config) -> None:
        self.config: model.Config = config
        self.executor: Executor = MonitoringProcessPoolExecutor(max_workers=self.config.browser.max_tabs)
        self.connection: AbstractRobustConnection
        self.channel: AbstractChannel
        self.queue: AbstractQueue

    async def connect(self) -> None:
        retries = 0
        max_retries = 5
        delay = 5

        while retries < max_retries:
            try:
                self.connection = await aio_pika.connect_robust(url=self.config.rabbitmq.get_connection_url())
                self.channel = await self.connection.channel()

                await self.channel.set_qos(prefetch_count=self.config.browser.max_tabs)
                self.queue = await self.channel.declare_queue(name=self.config.rabbitmq.url_queue, durable=False)
                await self.queue.consume(self._handle_message)
                print("Connected to RabbitMQ.")
                break  # Break out of the retry loop once connected

            except Exception as e:
                retries += 1
                print(f"Error connecting to RabbitMQ, retry {retries}/{max_retries}: {e}")
                if retries >= max_retries:
                    raise  # After max retries, give up and raise the exception
                time.sleep(delay)  # Wait before retrying

    async def _handle_message(self, message: aio_pika.IncomingMessage) -> None:
        url: str = message.body.decode()

        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, process_message, url, self.config)
        await message.ack()

    async def consume(self) -> None:
        await self.connect()

        print("Waiting for messages. To exit press CTRL+C")

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                if message is None:
                    break
                # Create a task for each message to be handled concurrently
                asyncio.create_task(self._handle_message(message))

    async def close(self) -> None:
        logging.info("Closing worker RabbitMQ Connection")
        await self.connection.close()
        logging.info("Shutting down process pool")
        self.executor.shutdown(wait=True)
        exit(0)


async def main() -> None:
    # Load config
    with open("config/config.yaml", "r") as f_obj:
        config: model.Config = model.Config.from_dict(yaml.safe_load(f_obj))

    consumer = Consumer(config)

    try:
        await consumer.consume()
    finally:
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
