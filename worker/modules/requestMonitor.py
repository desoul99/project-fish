import asyncio
import base64
import hashlib
import logging
import time
import typing
from concurrent.futures import ProcessPoolExecutor

import nodriver
from nodriver import cdp
from nodriver.cdp.fetch import RequestPattern
from nodriver.cdp.network import ResourceType

ALLOWED_RESOURCETYPES: list[ResourceType] = [cdp.network.ResourceType.XHR, cdp.network.ResourceType.DOCUMENT, cdp.network.ResourceType.IMAGE, cdp.network.ResourceType.MEDIA, cdp.network.ResourceType.OTHER, cdp.network.ResourceType.STYLESHEET, cdp.network.ResourceType.FONT, cdp.network.ResourceType.SCRIPT, cdp.network.ResourceType.FETCH, cdp.network.ResourceType.PING]
REQUEST_PAUSE_PATTERN: list[RequestPattern] = [cdp.fetch.RequestPattern(request_stage=cdp.fetch.RequestStage.RESPONSE)]
REDIRECT_STATUS_CODES: set[int] = {300, 301, 302, 303, 304, 305, 306, 307, 308}


class PausedResponse(typing.TypedDict):
    paused_response: cdp.fetch.RequestPaused
    body: typing.Optional[bytes]
    sha256_hash: typing.Optional[str]


def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RequestMonitor:
    def __init__(self, loop) -> None:
        self.responses: list[cdp.network.ResponseReceived] = []
        self.requests: list[cdp.network.RequestWillBeSent] = []

        self.paused_requests: list[cdp.fetch.RequestPaused] = []
        self.paused_responses: list[PausedResponse] = []

        self.paused_requests_queue = asyncio.Queue()

        self.hashing_process_pool = ProcessPoolExecutor(max_workers=5)

        self.request_handling_tasks: list[asyncio.Task] = []

        self.last_request_time: float

        self.loop: asyncio.AbstractEventLoop = loop

    def __del__(self) -> None:
        self.hashing_process_pool.shutdown()

    async def listen(self, tab: nodriver.Tab) -> None:
        """
        Sets up event listeners for network activity on the given tab and enables request interception.

        This function registers handlers for various network events such as request interception and
        response reception, allowing the system to capture and handle HTTP requests and responses
        made by the browser.
        """

        async def _response_handler(evt: cdp.network.ResponseReceived) -> None:
            self.responses.append(evt)

        async def _request_handler(evt: cdp.network.RequestWillBeSent) -> None:
            self.last_request_time = time.monotonic()
            self.requests.append(evt)

        async def _fetch_request_paused_handler(evt: cdp.fetch.RequestPaused) -> None:
            await self.paused_requests_queue.put(evt)
            logging.debug(f"Element {evt.request_id} put in queue")

        tab.add_handler(cdp.fetch.RequestPaused, _fetch_request_paused_handler)
        await tab.send(cdp.fetch.enable(REQUEST_PAUSE_PATTERN))
        await tab.send(cdp.network.set_cache_disabled(True))

        tab.add_handler(cdp.network.ResponseReceived, _response_handler)
        tab.add_handler(cdp.network.RequestWillBeSent, _request_handler)

        handle_paused_requests_task: asyncio.Task = self.loop.create_task(self._handle_paused_requests_loop(tab))

        # Add a callback to be notified if the task fails
        def _task_done_callback(fut) -> None:
            try:
                fut.result()  # This will raise any exceptions that occurred in the task
            except Exception as e:
                print(f"Task failed with exception: {e}")

        handle_paused_requests_task.add_done_callback(_task_done_callback)

    async def _async_sha256_hash(self, data: bytes) -> str:
        return await self.loop.run_in_executor(self.hashing_process_pool, sha256_hash, data)

    async def _handle_paused_response(self, evt: cdp.fetch.RequestPaused, tab: nodriver.Tab) -> None:
        """
        Handles a paused response and determines the appropriate action based on the response headers, trying to retrieve the response body if possible.
        """
        body = None

        if evt.response_headers is None:
            # No headers
            pass
        elif next((int(header.value) for header in (evt.response_headers or []) if header.name.lower() == "content-length"), 0) == 0:
            # No content
            pass
        elif evt.response_status_code in REDIRECT_STATUS_CODES and any(h.name.lower() == "location" for h in evt.response_headers):
            # Redirect
            pass
        else:
            response_body = await tab.send(cdp.fetch.get_response_body(evt.request_id))
            if response_body:
                body, is_base64 = response_body
                body = base64.b64decode(body) if is_base64 else body.encode("utf-8")
            else:
                logging.info(f"Failed to get response body for {str(evt.request_id)}")

        await tab.send(cdp.fetch.continue_response(evt.request_id))

        if body:
            hash = await self._async_sha256_hash(body)
            self.paused_responses.append(PausedResponse(paused_response=evt, body=body, sha256_hash=hash))
        else:
            self.paused_responses.append(PausedResponse(paused_response=evt))

    async def _handle_paused_request(self, evt: cdp.fetch.RequestPaused, tab: nodriver.Tab):
        """
        Handles a paused request by continuing the request process
        """
        await tab.send(cdp.fetch.continue_request(evt.request_id))

    async def _handle_paused_requests_loop(self, tab: nodriver.Tab) -> None:
        """
        Loop that awaits new cdp.fetch.RequestPaused added to a Queue, identifies their time and handles them accordingly through the use of:
        - self.handle_paused_response()
        - self.handle_paused_request()
        """

        def _remove_completed_task(task: asyncio.Task) -> None:
            """Remove the task from the running_tasks list when it's done."""
            try:
                # Ensure any exception in the task is re-raised for logging/debugging
                task.result()
            except Exception as e:
                logging.error(f"Task failed with exception: {e}")
            finally:
                # Remove the completed task from the running list
                self.request_handling_tasks.remove(task)

        while True:
            logging.debug("Awaiting Items")
            evt: cdp.fetch.RequestPaused = await self.paused_requests_queue.get()
            logging.debug(f"Got item {evt.request_id} from queue")

            if any(value is not None for value in [evt.response_error_reason, evt.response_status_code]):
                logging.debug(f"Handling {evt.request_id} as response")
                task: asyncio.Task = self.loop.create_task(self._handle_paused_response(evt, tab))
            else:
                logging.debug(f"Handling {evt.request_id} as request")
                task: asyncio.Task = self.loop.create_task(self._handle_paused_request(evt, tab))

            task.add_done_callback(_remove_completed_task)
            self.request_handling_tasks.append(task)

    async def wait_for_completion(self, tab: nodriver.Tab, timeout: float) -> None:
        starting_time = time.monotonic()
        current_time = starting_time
        sleep_time = timeout / 60

        while (current_time - starting_time) < timeout:
            if current_time - self.last_request_time > 1:
                if len(self.request_handling_tasks) == 0:
                    return

            await asyncio.sleep(sleep_time)
            current_time = time.monotonic()

    def get_data(self) -> str:
        return "Temp"

    def print_data(self) -> None:
        print("Requests: " + str(len(self.requests)))
        print("Responses: " + str(len(self.responses)))
        print("Paused Responses: " + str(len(self.paused_responses)))
        print("Paused Responses body: " + str(len([response for response in self.paused_responses if response.get("body")])))

        missing_paused_responses: list = []
        if len(self.responses) != len(self.paused_responses):
            for response in self.responses:
                missing = True
                for paused_response in self.paused_responses:
                    if response.response.url == paused_response.get("paused_response").request.url:
                        missing = False
                        break
                if missing:
                    missing_paused_responses.append(response.response.url)

        missing_responses: list = []
        if len(self.requests) != len(self.responses):
            for request in self.requests:
                missing = True
                for response in self.responses:
                    if response.request_id == request.request_id:
                        missing = False
                        break
                if missing:
                    missing_responses.append(request.request.url)

        print("Missing responses: " + str(len(missing_responses)))
        print("Missing responses: " + "\n".join(missing_responses))

        print("Missing paused responses: " + str(len(missing_paused_responses)))
        print("Missing paused responses: " + "\n".join(missing_paused_responses))

        print("Running handling tasks: " + str(len(self.request_handling_tasks)))

    def print_running_tasks(self) -> None:
        print("Running handling tasks: " + str(len(self.request_handling_tasks)))
