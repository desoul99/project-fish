import asyncio
import logging
import signal
import nodriver
import pymongo
import uuid

import pymongo.synchronous.collection
import pymongo.synchronous.database

from model import model
from modules.requestMonitor import RequestMonitor


class WorkerBrowser:
    def __init__(self, config: model.Config) -> None:
        self.config: model.Config = config
        self.mongo_client = pymongo.MongoClient(self.config.mongodb.get_connection_url(), uuidRepresentation="standard")
        self.mongo_db: pymongo.synchronous.database.Database = self.mongo_client[self.config.mongodb.database]
        self.mongo_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config.mongodb.collection]
        self.scan_id: uuid.UUID = uuid.uuid4()
        self.loop: asyncio.AbstractEventLoop = nodriver.loop()
        self.browser: nodriver.Browser

        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame) -> None:
        self.close()
        exit(0)

    def close(self) -> None:
        # If a browser instance exists, close it
        if self.browser:
            self.browser.stop()
            logging.info("Browser closed.")

        if self.mongo_client:
            self.mongo_client.close()
            logging.info("MongoDB connection closed.")

    async def load(self, url) -> None:
        if not url.startswith("http"):
            url: str = "https://" + url

        try:
            await self.main(url)
        except asyncio.CancelledError:
            logging.info("Task cancellation detected! Exiting gracefully..")
        except KeyboardInterrupt:
            logging.info("CTRL+C detected! Exiting gracefully...")
        finally:
            self.close()

    async def main(self, url: str) -> None:
        self.browser = await nodriver.start(browser_args=self.config.browser.execution_args, browser_executable_path=self.config.browser.executable_path, headless=False)

        monitor = RequestMonitor(self.loop)
        tab: nodriver.Tab = await self.browser.get("about:blank")

        await monitor.listen(tab)

        await tab.get(url)

        await monitor.wait_for_completion(tab)

        await tab
