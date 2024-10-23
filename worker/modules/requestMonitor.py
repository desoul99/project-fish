import asyncio
import base64
import hashlib
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

import nodriver
from model.model import PausedResponseDict
from nodriver import cdp
from nodriver.cdp.fetch import RequestPattern
from nodriver.cdp.network import ResourceType


def sha256_hash(data: bytes) -> str:
    """
    Returns the hexdigested SHA256 hash of the given data.
    """
    return hashlib.sha256(data).hexdigest()


class RequestMonitor:
    """
    A class that monitors and intercepts browser network requests and responses,
    trying to intercept and save the response data where possible.
    """

    ALLOWED_RESOURCETYPES: list[ResourceType] = [cdp.network.ResourceType.XHR, cdp.network.ResourceType.DOCUMENT, cdp.network.ResourceType.IMAGE, cdp.network.ResourceType.MEDIA, cdp.network.ResourceType.OTHER, cdp.network.ResourceType.STYLESHEET, cdp.network.ResourceType.FONT, cdp.network.ResourceType.SCRIPT, cdp.network.ResourceType.FETCH, cdp.network.ResourceType.PING]
    REQUEST_PAUSE_PATTERN: list[RequestPattern] = [cdp.fetch.RequestPattern(request_stage=cdp.fetch.RequestStage.RESPONSE)]
    REDIRECT_STATUS_CODES: set[int] = {300, 301, 302, 303, 304, 305, 306, 307, 308}
    EMULATION_DEVICES = {
        "pixel7": {
            "device_metrics": {
                "width": 980,
                "height": 2170,
                "device_scale_factor": 2.6249998807907104,
                "mobile": True,
                "scale": None,  # optional
                "screen_width": 412,  # optional
                "screen_height": 915,  # optional
                "position_x": None,  # optional
                "position_y": None,  # optional
                "dont_set_visible_size": False,  # optional
                "screen_orientation": cdp.emulation.ScreenOrientation("landscapePrimary", 0),  # optional
                "viewport": None,  # optional
                "display_feature": None,  # optional
                "device_posture": None,  # optional
            },
            "user_agent_override": {"user_agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36", "accept_language": "it-IT,it,en-US,en", "platform": "Linux armv81"},
            "is_mobile": True,
            "accepted_encodings": [cdp.network.ContentEncoding(value="gzip"), cdp.network.ContentEncoding(value="deflate")],
        }
    }

    def __init__(self, loop: asyncio.AbstractEventLoop, max_content_size: int, emulate_device: Optional[str] = None, page_cookies: Optional[list[cdp.network.CookieParam]] = None) -> None:
        self.responses: list[cdp.network.ResponseReceived] = []
        self.requests: list[cdp.network.RequestWillBeSent] = []

        self.paused_responses: list[PausedResponseDict] = []

        self.paused_requests_queue = asyncio.Queue()

        self.hashing_process_pool: Optional[ProcessPoolExecutor]

        self.request_handling_tasks: list[asyncio.Task] = []

        self.last_request_time: float

        self.emulate_device: Optional[str] = emulate_device
        self.page_cookies: Optional[list[cdp.network.CookieParam]] = page_cookies

        self.max_content_size: int = max_content_size
        self.loop: asyncio.AbstractEventLoop = loop

    def __enter__(self) -> "RequestMonitor":
        self.hashing_process_pool = ProcessPoolExecutor(max_workers=5)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self.hashing_process_pool:
            self.hashing_process_pool.shutdown(wait=True)

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
        await tab.send(cdp.fetch.enable(RequestMonitor.REQUEST_PAUSE_PATTERN))
        await tab.send(cdp.network.set_cache_disabled(True))

        tab.add_handler(cdp.network.ResponseReceived, _response_handler)
        tab.add_handler(cdp.network.RequestWillBeSent, _request_handler)

        # Setup cookie settings
        if self.page_cookies:
            await tab.send(cdp.network.set_cookies(self.page_cookies))

        # Setup device emulation settings
        if self.emulate_device and self.emulate_device in RequestMonitor.EMULATION_DEVICES.keys():
            await tab.send(cdp.emulation.set_device_metrics_override(**RequestMonitor.EMULATION_DEVICES[self.emulate_device]["device_metrics"]))
            await tab.send(cdp.network.set_user_agent_override(**RequestMonitor.EMULATION_DEVICES[self.emulate_device]["user_agent_override"]))
            await tab.send(cdp.emulation.set_user_agent_override(**RequestMonitor.EMULATION_DEVICES[self.emulate_device]["user_agent_override"]))
            if RequestMonitor.EMULATION_DEVICES[self.emulate_device]["is_mobile"]:
                await tab.send(cdp.emulation.set_touch_emulation_enabled(enabled=True))
            if RequestMonitor.EMULATION_DEVICES[self.emulate_device]["accepted_encodings"]:
                await tab.send(cdp.network.set_accepted_encodings())

        handle_paused_requests_task: asyncio.Task = self.loop.create_task(self._handle_paused_requests_loop(tab))

        # Add a callback to be notified if the task fails
        def _task_done_callback(fut) -> None:
            try:
                fut.result()  # This will raise any exceptions that occurred in the task
            except Exception as e:
                logging.debug(f"Task failed with exception: {e}")

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
        elif next((int(header.value) for header in (evt.response_headers or []) if header.name.lower() == "content-length"), 100) == 0:
            # No content
            pass
        elif next((int(header.value) for header in (evt.response_headers or []) if header.name.lower() == "content-length"), 0) > self.max_content_size:
            # Content-length greater than max_content_size
            pass
        elif evt.response_status_code in RequestMonitor.REDIRECT_STATUS_CODES and any(h.name.lower() == "location" for h in evt.response_headers):
            # Redirect
            pass
        else:
            response_body = await tab.send(cdp.fetch.get_response_body(evt.request_id))
            if response_body:
                body, is_base64 = response_body
                body = base64.b64decode(body) if is_base64 else body.encode("utf-8")
            else:
                logging.debug(f"Failed to get response body for {str(evt.request_id)}")

        await tab.send(cdp.fetch.continue_response(evt.request_id))

        if body:
            hash = await self._async_sha256_hash(body)
            self.paused_responses.append(PausedResponseDict(paused_response=evt, body=body, sha256_hash=hash))
        else:
            self.paused_responses.append(PausedResponseDict(paused_response=evt))

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
            if current_time - self.last_request_time > 2:
                if len(self.request_handling_tasks) == 0:
                    return

            await asyncio.sleep(sleep_time)
            current_time = time.monotonic()
