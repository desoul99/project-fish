import asyncio
import functools
import logging
import multiprocessing
import time
import uuid
from concurrent.futures import Executor, Future, ProcessPoolExecutor

import aio_pika
import yaml
from aio_pika.abc import AbstractChannel, AbstractQueue, AbstractRobustConnection
from model import model
from modules.browser import WorkerBrowser
from modules.database import Database
from modules.encoders import DataProcessor
from modules.requestMonitor import RequestMonitor

logging.basicConfig(level=logging.WARNING)


def timeit(func):
    """
    Decorator to measure the execution time of a function using time.perf_counter.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        pid = multiprocessing.current_process().pid
        logging.debug(f"{func.__name__} in process {pid} started execution.")
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        logging.debug(f"{func.__name__} in process {pid} executed in {elapsed_time:.6f} seconds.")
        return result

    return wrapper


# Debugging purposes
class MonitoringProcessPoolExecutor(ProcessPoolExecutor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _adjust_process_count(self):
        super()._adjust_process_count()
        logging.debug(f"Current active processes: {len(self._processes)}")

    def submit(self, fn, *args, **kwargs):
        logging.debug(f"Submitting task {fn.__name__} with args: {args}")
        future = super().submit(fn, *args, **kwargs)
        future.add_done_callback(self._on_task_complete)
        return future

    def _on_task_complete(self, future: Future):
        exception = future.exception()
        if exception is None:
            logging.debug(f"Task completed successfully. Result: {future.result()}")
        else:
            logging.debug(f"Task raised an exception: {exception}")
        # Optional: Print current process count after task completion
        logging.debug(f"Current active processes: {len(self._processes)}")


@timeit
def process_message(url: str, config: model.Config) -> None:
    scan_id: uuid.UUID = uuid.uuid4()

    browser = WorkerBrowser(config.browser)
    request_monitor = RequestMonitor(browser.loop)
    database = Database(config.mongodb, config.redis)

    browser.set_request_monitor(request_monitor)
    browser.loop.run_until_complete(browser.load(url))

    formatted_requests, formatted_content = DataProcessor.process_requests(scan_id, url, request_monitor)

    database.insert_requests(formatted_requests)
    database.insert_content(formatted_content)


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
                logging.debug("Connected to RabbitMQ.")
                break  # Break out of the retry loop once connected

            except Exception as e:
                retries += 1
                logging.warning(f"Error connecting to RabbitMQ, retry {retries}/{max_retries}: {e}")
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

        logging.info("Waiting for messages. To exit press CTRL+C")

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                if message is None:
                    break
                # Create a task for each message to be handled concurrently
                asyncio.create_task(self._handle_message(message))

    async def close(self) -> None:
        logging.debug("Closing worker RabbitMQ Connection")
        await self.connection.close()
        logging.debug("Shutting down process pool")
        self.executor.shutdown(wait=True)


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
