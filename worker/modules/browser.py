import asyncio
import logging
import nodriver
import uuid

from model import model
from modules.requestMonitor import RequestMonitor


class WorkerBrowser:
    def __init__(self, config: model.BrowserConfig) -> None:
        self.config: model.BrowserConfig = config

        self.loop: asyncio.AbstractEventLoop = nodriver.loop()
        self.scan_id: uuid.UUID = uuid.uuid4()

        self.request_monitor: RequestMonitor
        self.browser: nodriver.Browser

    def set_request_monitor(self, request_monitor: RequestMonitor):
        self.request_monitor = request_monitor

    def close(self) -> None:
        # If a browser instance exists, close it
        if self.browser:
            self.browser.stop()
            logging.info("Browser closed.")

    async def load(self, url) -> None:
        if not url.startswith("http"):
            url: str = "https://" + url

        try:
            await self.main(url)
        finally:
            self.close()

    async def main(self, url: str) -> None:
        self.browser = await nodriver.start(browser_args=self.config.execution_args, browser_executable_path=self.config.executable_path, headless=False)

        tab: nodriver.Tab = await self.browser.get("about:blank")

        await self.request_monitor.listen(tab)

        await tab.get(url)

        await self.request_monitor.wait_for_completion(tab)

        await tab
