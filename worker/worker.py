import asyncio
import configparser
import functools
import json
import logging
import logging.config
import multiprocessing
import time
from typing import Optional
import uuid
from concurrent.futures import Executor, Future, ProcessPoolExecutor

import aio_pika
import yaml
from aio_pika.abc import AbstractChannel, AbstractQueue, AbstractRobustConnection
from model import model
from modules.browser import WorkerBrowser
from modules.requestContentStorage import RequestContentStorage
from modules.encoders import DataProcessor
from modules.requestMonitor import RequestMonitor
from modules.emulation import Emulation

# Load logging configuration from the INI file
config = configparser.ConfigParser()
config.read("config/logging_config.ini")

# Configure logging
logging.config.fileConfig(config)


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
def process_message(message: model.RabbitMQMessage, config: model.Config) -> None:
    scan_id: uuid.UUID = uuid.uuid4()

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    with RequestMonitor(loop=loop, max_content_size=config.browser.max_content_size, emulation_device=message.emulation_device, proxy=message.proxy, page_cookies=message.page_cookies) as request_monitor, WorkerBrowser(config.browser, request_monitor) as browser, RequestContentStorage(config.mongodb, config.redis) as request_content_storage:
        try:
            loop.run_until_complete(asyncio.wait_for(browser.main(message.url), timeout=config.browser.browser_timeout))

            formatted_requests: model.ProcessedDataDict = DataProcessor.format_requests(scan_id, message.url, request_monitor, config)
            request_content_storage.insert_requests(formatted_requests)

            formatted_content: list[model.ResponseContentDict] = DataProcessor.format_content(request_monitor)
            request_content_storage.insert_content(formatted_content)

            formatted_certificates = DataProcessor.format_certificates(request_monitor)
            request_content_storage.insert_certificates(formatted_certificates)

        except asyncio.TimeoutError:
            logging.error(f"Timeout error while analyzing url: {message.url}")
            raise


class Consumer:
    def __init__(self, config: model.Config) -> None:
        self.config: model.Config = config
        self.emulation_validator: Optional[Emulation] = None
        self.executor: Optional[Executor] = None
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: AbstractChannel
        self.queue: AbstractQueue

    async def __aenter__(self) -> "Consumer":
        self.executor = MonitoringProcessPoolExecutor(max_workers=self.config.browser.max_tabs)
        self.emulation_validator = Emulation(self.config.emulation)
        try:
            await self.connect()
        except Exception as e:
            logging.error("Error occurred while connecting to RabbitMQ: %s", e)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        try:
            await self.close()
        except Exception as e:
            logging.error("Error occurred while closing RabbitMQ Connection and proces pool: %s", e)
            raise

    async def close(self) -> None:
        if self.connection:
            try:
                logging.debug("Closing worker RabbitMQ Connection")
                await self.connection.close()
            except Exception as e:
                logging.error("Error closing RabbitMQ Connection: %s", e)
                raise

        if self.executor:
            try:
                logging.debug("Shutting down process pool")
                self.executor.shutdown(wait=True)
            except Exception as e:
                logging.error("Error shutting down process pool: %s", e)
                raise

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
        try:
            converted_message = model.RabbitMQMessage.from_dict(json.loads(message.body), emulation=self.emulation_validator)
        except (ValueError, KeyError) as e:
            await message.reject(requeue=False)
            logging.error(f"Message was not properly formatted: {e}")
            return

        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self.executor, process_message, converted_message, self.config)
            await message.ack()
        except Exception as e:
            # Catch any other exceptions
            await message.reject(requeue=True)
            logging.error(f"Error occurred while processing message: {e}")

    async def consume(self) -> None:
        if not self.connection:
            raise RuntimeError("Consumer is not connected to RabbitMQ.")

        logging.info("Waiting for messages. To exit press CTRL+C")

        try:
            async with self.queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if message is None:
                        break
                    # Create a task for each message to be handled concurrently
                    asyncio.create_task(self._handle_message(message))
        except asyncio.CancelledError:
            pass


async def main() -> None:
    # Load config
    with open("config/config.yaml", "r") as f_obj:
        config: model.Config = model.Config.from_dict(yaml.safe_load(f_obj))

    async with Consumer(config) as consumer:
        await consumer.consume()


if __name__ == "__main__":
    asyncio.run(main())
