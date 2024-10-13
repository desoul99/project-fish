import asyncio
import logging
import time

import nodriver as uc
from modules.requestMonitor import RequestMonitor

logging.basicConfig(level=logging.DEBUG)


async def crawl(loop) -> None:
    # Start the browser

    browser: uc.Browser = await uc.start(headless=False, browser_executable_path="/usr/bin/google-chrome-stable")
    monitor = RequestMonitor(loop)

    tab: uc.Tab = await browser.get("about:blank")

    input("press any key")

    # Add network listener
    await monitor.listen(tab)

    start_time: float = time.time()
    await tab.get("https://bing.com")

    logging.debug("Awaiting Tab1")
    await tab
    logging.debug("Awaited Tab1")

    monitor.print_running_tasks()

    end_time: float = time.time()
    elapsed_time: float = end_time - start_time
    print(f"Elapsed Time: {elapsed_time:.6f} seconds")

    monitor.print_data()

    time.sleep(1000)


if __name__ == "__main__":
    loop: asyncio.AbstractEventLoop = uc.loop()
    loop.set_debug(False)
    loop.run_until_complete(crawl(loop))
