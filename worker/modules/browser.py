import asyncio
import logging
import time
from typing import Optional

import nodriver
from model import model
from modules.requestMonitor import RequestMonitor

from unittest.mock import patch


class WorkerBrowser:
    def __init__(self, config: model.BrowserConfig, request_monitor: RequestMonitor) -> None:
        self.config: model.BrowserConfig = config
        self.request_monitor: RequestMonitor = request_monitor
        self.browser: Optional[nodriver.Browser] = None

    def __enter__(self) -> "WorkerBrowser":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self.browser:
            self.browser.stop()
            with patch("builtins.print"):
                # Avoid littering the console with print statement inside deconstruct_browser()
                nodriver.util.deconstruct_browser()
            logging.debug("Browser closed.")

    async def main(self, url: str) -> None:
        self.browser = await nodriver.start(browser_args=self.config.execution_args, browser_executable_path=self.config.executable_path, headless=False)

        tab: nodriver.Tab = await self.browser.get("about:blank")

        await self.request_monitor.listen(tab)

        await tab.get(url)

        pageload_starting_time = time.monotonic()
        try:
            await asyncio.wait_for(tab, timeout=self.config.pageload_timeout)
            remaining_pageload_timeout = self.config.pageload_timeout - (time.monotonic() - pageload_starting_time)
            await self.request_monitor.wait_for_completion(tab, remaining_pageload_timeout, self.config.min_request_wait)
        except asyncio.TimeoutError:
            pass

        await self.request_monitor.finalize_monitoring(tab)
