from nodriver import start, cdp
from nodriver.core.browser import Browser
import pymongo
import uuid

import pymongo.synchronous
import pymongo.synchronous.collection
import pymongo.synchronous.database

from model import model


class WorkerBrowser:
    def __init__(self, config: model.Config) -> None:
        self.config: model.Config = config
        self.mongo_client = pymongo.MongoClient(self.config.mongodb.get_connection_url(), uuidRepresentation="standard")
        self.mongo_db: pymongo.synchronous.database.Database = self.mongo_client[self.config.mongodb.database]
        self.mongo_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config.mongodb.collection]
        self.scan_id = uuid.uuid4()
        self.requests = {"scan_id": self.scan_id, "requests": [], "hashes": []}
        loop().run_until_complete(self.start_browser())

    async def start_browser(self) -> None:
        self.browser: Browser = await start(
            browser_args=self.config.browser.execution_args,
            browser_executable_path=self.config.browser.executable_path,
        )

    def load(self, url):
        if not url.startswith("http"):
            url = "https://" + url

        loop().run_until_complete(self.main(url))

    async def main(self, url):
        self.main_tab = self.browser.main_tab
        await self.main_tab.send(cdp.network.set_cache_disabled(True))
        self.main_tab.add_handler(cdp.network.RequestWillBeSent, self.send_handler)
        self.main_tab.add_handler(cdp.network.ResponseReceived, self.receive_handler)
        page = await self.browser.get(url)
        retries = 0
        while retries < 7:
            if sum(1 for dictionary in self.requests["requests"] if (len(dictionary) == 1) or (dictionary["request"]["redirect_response"] is None)) > 0:
                await page.wait(t=2)
                retries = retries + 1
        await page
        self.mongo_collection.insert_one(self.requests)
        self.browser.stop()

    async def receive_handler(self, event: cdp.network.ResponseReceived):
        response = ResponseEncoder(event)
        if not response["response"]["url"].startswith("chrome") and response["response"].get("remoteIPAddress", False):
            res = next((req for req in self.requests["requests"] if req["request"]["request_id"] == response["request_id"]), None)
            if res:
                index = self.requests["requests"].index(res)
                self.requests["requests"][index]["response"] = response
            if response["response"].get("headers", False) and response["response"]["headers"].get("pf_sha256", False):
                self.requests["hashes"].append(response["response"]["headers"]["pf_sha256"])

    async def send_handler(self, event: cdp.network.RequestWillBeSent):
        request = RequestEncoder(event)
        initiator = request["initiator"].get("url", "") if request.get("initiator", False) else ""
        if not request["request"]["url"].startswith("chrome") and not initiator.startswith("chrome"):
            self.requests["requests"].append({"request": request})
