import asyncio
import nodriver as uc
from nodriver import cdp
import time
import typing
import os
import hashlib
import base64

allowed_resourceTypes = [
    cdp.network.ResourceType.XHR, cdp.network.ResourceType.DOCUMENT, cdp.network.ResourceType.IMAGE,
    cdp.network.ResourceType.MEDIA, cdp.network.ResourceType.OTHER, cdp.network.ResourceType.STYLESHEET,
    cdp.network.ResourceType.FONT, cdp.network.ResourceType.SCRIPT, cdp.network.ResourceType.FETCH, cdp.network.ResourceType.PING
]

# Define a TypedDict for the response type
class ResponseType(typing.TypedDict):
    url: str
    body: str
    is_base64: bool

class RequestMonitor:
    def __init__(self):
        self.requests: list[list[str | cdp.network.RequestId]] = []
        self.last_request: float | None = None
        self.lock = asyncio.Lock()

    async def listen(self, page: uc.Tab):
        async def handler(evt: cdp.network.ResponseReceived):
            async with self.lock:
                if evt.response.encoded_data_length > 0 and evt.type_ in allowed_resourceTypes:
                    self.requests.append([evt.response.url, evt.request_id])
                    self.last_request = time.time()
                elif evt.response.encoded_data_length > 0:
                    print(f'EVENT PERCEIVED BY BROWSER IS: {evt.type_}, {evt.type_ in allowed_resourceTypes}')

        page.add_handler(cdp.network.ResponseReceived, handler)

    async def receive(self, page: uc.Tab):
        responses: list[ResponseType] = []
        retries = 0
        max_retries = 5

        # Wait at least 2 seconds after the last XHR request
        while True:
            if self.last_request is None or retries > max_retries:
                break

            if time.time() - self.last_request <= 5:
                retries += 1
                await asyncio.sleep(2)
                continue
            else:
                break

        await page  # Wait for the page operation to complete

        async with self.lock:
            print(f"total requests: {len(self.requests)}")
            for request in self.requests:
                try:
                    if not isinstance(request[1], cdp.network.RequestId):
                        raise ValueError('Request ID is not of type RequestId')

                    res = await page.send(cdp.network.get_response_body(request[1]))
                    if res is None:
                        continue

                    # Prepare the response data
                    url = request[0]
                    body = res[0]  # Response body
                    is_base64 = res[1]  # Whether the response is base64 encoded
                    responses.append({'url': url, 'body': body, 'is_base64': is_base64})

                    # Save the response to a file
                    await self.save_response(url, body, is_base64)

                except Exception as e:
                    print(f'Error getting body for request {request[0]}: {e}')

        return responses

    async def save_response(self, url: str, body: str, is_base64: bool):
        """Save the response to a file based on the request URL"""
        # Create a unique filename using the URL (hashed)
        filename = self.generate_filename(url)
        file_path = f"responses/{filename}"

        # Ensure the directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # If the content is base64-encoded, decode it
        if is_base64:
            body = base64.b64decode(body)

        # Write the response body to a file (binary mode for base64, text mode otherwise)
        mode = 'wb' if is_base64 else 'w'
        with open(file_path, mode) as f:
            f.write(body)

        #print(f"Response saved to {file_path}")

    def generate_filename(self, url: str) -> str:
        """Generate a unique filename based on the URL using SHA256 hash"""
        #url_hash = hashlib.sha256(url.encode()).hexdigest()
        #return f"{url_hash}.txt"
        return url.encode()[:150]

async def crawl():
    # Start the browser
    browser = await uc.start(headless=False)
    monitor = RequestMonitor()

    tab = await browser.get('about:blank')

    # Add network listener
    await monitor.listen(tab)

    # Change the URL based on use case
    tab = await browser.get('https://bing.com')

    monitor.print_requests()
    
    # Get the responses and process them
    #xhr_responses = await monitor.receive(tab)

if __name__ == '__main__':
    uc.loop().run_until_complete(crawl())
