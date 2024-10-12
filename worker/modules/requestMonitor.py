import asyncio
import nodriver as uc
from nodriver import cdp
import time
import typing
import logging

# from .encoders import RequestEncoder, ResponseEncoder


logging.basicConfig(level=logging.INFO)


allowed_resourceTypes = [
    cdp.network.ResourceType.XHR,
    cdp.network.ResourceType.DOCUMENT,
    cdp.network.ResourceType.IMAGE,
    cdp.network.ResourceType.MEDIA,
    cdp.network.ResourceType.OTHER,
    cdp.network.ResourceType.STYLESHEET,
    cdp.network.ResourceType.FONT,
    cdp.network.ResourceType.SCRIPT,
    cdp.network.ResourceType.FETCH,
    cdp.network.ResourceType.PING,
]


# Define a TypedDict for the response type
class ResponseType(typing.TypedDict):
    request_id: cdp.network.RequestId
    body: str
    is_base64: bool


class RequestMonitor:
    def __init__(self, loop):
        self.responses: cdp.network.ResponseReceived = []
        self.requests: cdp.network.RequestWillBeSent = []
        self.paused_requests: cdp.fetch.RequestPaused = []
        self.paused_responses: cdp.fetch.RequestPaused = []
        self.paused_requests_queue = asyncio.Queue()
        self.loop = loop

    async def listen(self, page: uc.Tab):
        async def response_handler(evt: cdp.network.ResponseReceived):
            self.responses.append(evt)

        async def request_handler(evt: cdp.network.RequestWillBeSent):
            initiator_url = getattr(evt.initiator, "url", "") or ""
            request_url = getattr(evt.request, "url", "") or ""

            if not (request_url.startswith("chrome") or request_url.startswith("blob:") or initiator_url.startswith("chrome")):
                self.requests.append(evt)

        async def fetch_request_paused_handler(evt: cdp.fetch.RequestPaused):
            # self.paused_requests.append(evt)
            await self.paused_requests_queue.put(evt)
            logging.info(f"Element {evt.request_id} put in queue")

        pause_pattern = [cdp.fetch.RequestPattern(request_stage=cdp.fetch.RequestStage.RESPONSE)]

        page.add_handler(cdp.fetch.RequestPaused, fetch_request_paused_handler)
        await page.send(cdp.fetch.enable(pause_pattern))

        # page.add_handler(cdp.network.ResponseReceived, response_handler)
        page.add_handler(cdp.network.RequestWillBeSent, request_handler)

    async def handle_paused_response(self, evt: cdp.fetch.RequestPaused, page: uc.Tab):
        # Response stage

        self.paused_responses.append(evt)

        if not evt.response_headers:
            await page.send(cdp.fetch.continue_response(evt.request_id))
            return

        content_length = next((int(header.value) for header in evt.response_headers if header.name.lower() == "content-length"), 0)

        if content_length == 0:
            await page.send(cdp.fetch.continue_response(evt.request_id))
            return

        if evt.response_status_code in [300, 301, 302, 303, 304, 305, 306, 307, 308] and any(h.name.lower() == "location" for h in evt.response_headers):
            # Redirect
            pass
        else:
            c = await page.send(cdp.fetch.get_response_body(evt.request_id))
            if c is not None:
                pass
            else:
                logging.info(f"Failed to get response body for {str(evt.request_id)}")

        await page.send(cdp.fetch.continue_response(evt.request_id))

    async def handle_paused_request(self, evt: cdp.fetch.RequestPaused, page: uc.Tab):
        # Request stage
        await page.send(cdp.fetch.continue_request(evt.request_id))

    async def handle_paused_requests(self, page: uc.Tab):
        while True:
            logging.info("Awaiting Items")
            evt = await self.paused_requests_queue.get()
            logging.info(f"Got item {evt.request_id} from queue")

            if any(value is not None for value in [evt.response_error_reason, evt.response_status_code]):
                logging.info(f"Handling {evt.request_id} as response")
                self.loop.create_task(self.handle_paused_response(evt, page))
            else:
                logging.info(f"Handling {evt.request_id} as request")
                self.loop.create_task(self.handle_paused_request(evt, page))

    def print_data(self):
        print("Requests: " + str(len(self.requests)))
        print("Responses: " + str(len(self.responses)))
        print("Paused Responses: " + str(len(self.paused_responses)))
        # print(self.responses[10])


async def crawl(loop):
    # Start the browser

    browser = await uc.start(headless=False, browser_executable_path="/usr/bin/google-chrome")
    monitor = RequestMonitor(loop)

    tab = await browser.get("about:blank")

    # input("press any key")

    loop.slow_callback_duration = 1  # 10 ms
    handle_paused_requests_task = loop.create_task(monitor.handle_paused_requests(tab))

    # Add a callback to be notified if the task fails
    def task_done_callback(fut):
        try:
            fut.result()  # This will raise any exceptions that occurred in the task
        except Exception as e:
            print(f"Task failed with exception: {e}")

    handle_paused_requests_task.add_done_callback(task_done_callback)

    # Add network listener
    await monitor.listen(tab)
    await tab.send(cdp.network.set_cache_disabled(True))

    logging.debug("Ok")
    start_time = time.time()
    await tab.send(cdp.page.navigate("https://bing.com"))
    logging.debug("Ok2")

    print("Awaiting Tab1")
    await tab
    print("Awaited Tab1")

    await asyncio.sleep(1)

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Elapsed Time: {elapsed_time:.6f} seconds")

    monitor.print_data()

    time.sleep(1000)


if __name__ == "__main__":
    loop = uc.loop()

    loop.set_debug(False)

    # import nodriver
    # logging.info(nodriver.__file__)

    loop.run_until_complete(crawl(loop))
