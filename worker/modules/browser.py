import asyncio
import logging
import time
import nodriver

from model import model
from modules.requestMonitor import RequestMonitor


class WorkerBrowser:
    def __init__(self, config: model.BrowserConfig) -> None:
        self.config: model.BrowserConfig = config

        self.loop: asyncio.AbstractEventLoop = nodriver.loop()

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

        pageload_starting_time = time.monotonic()
        try:
            await asyncio.wait_for(tab, timeout=self.config.pageload_timeout)
            remaining_pageload_timeout = self.config.pageload_timeout - (time.monotonic() - pageload_starting_time)
            await self.request_monitor.wait_for_completion(tab, remaining_pageload_timeout)
        except asyncio.TimeoutError:
            pass

        self.request_monitor.print_data()
