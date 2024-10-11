import asyncio
import nodriver as uc
from nodriver import cdp
import time
import typing
import os
import hashlib
import json
import base64
from tqdm import tqdm
#from .encoders import RequestEncoder, ResponseEncoder

allowed_resourceTypes = [
    cdp.network.ResourceType.XHR, cdp.network.ResourceType.DOCUMENT, cdp.network.ResourceType.IMAGE,
    cdp.network.ResourceType.MEDIA, cdp.network.ResourceType.OTHER, cdp.network.ResourceType.STYLESHEET,
    cdp.network.ResourceType.FONT, cdp.network.ResourceType.SCRIPT, cdp.network.ResourceType.FETCH, cdp.network.ResourceType.PING
]

# Define a TypedDict for the response type
class ResponseType(typing.TypedDict):
    request_id: cdp.network.RequestId
    body: str
    is_base64: bool

class RequestMonitor:
    def __init__(self):
        self.responses: list[cdp.network.RequestId] = []
        self.requests: list[cdp.network.RequestWillBeSent] = []
        self.last_request: float | None = None
        self.lock = asyncio.Lock()
    
    async def get_requests(self):
        async with self.lock:
            return len(self.requests), len(self.responses), len([request for request in self.requests if request.request_id not in self.responses and request.redirect_response is None and not request.request.url.startswith('data:')])
    
    async def get_missing_responses(self):
        print("awaiting lock")
        async with self.lock:
            print("got lock")
            return [request for request in self.requests if request.request_id not in self.responses and request.redirect_response is None and not request.request.url.startswith('data:')]

    async def listen(self, page: uc.Tab):
        async def response_handler(evt: cdp.network.ResponseReceived):
            if evt.response.encoded_data_length > 0 and evt.type_ in allowed_resourceTypes:
                async with self.lock:
                    self.responses.append(evt.request_id)
                    self.last_response = time.time()
            elif evt.response.encoded_data_length > 0:
                print(f'EVENT PERCEIVED BY BROWSER IS: {evt.type_}, {evt.type_ in allowed_resourceTypes}')
        
        async def request_handler(evt: cdp.network.RequestWillBeSent):
            initiator_url = getattr(evt.initiator, 'url', '') or ''
            request_url = getattr(evt.request, 'url', '') or ''
                
            if not (request_url.startswith('chrome') or request_url.startswith('blob:') or initiator_url.startswith('chrome')):
                async with self.lock:
                    self.requests.append(evt)

        page.add_handler(cdp.network.ResponseReceived, response_handler)
        page.add_handler(cdp.network.RequestWillBeSent, request_handler)

    async def receive(self, page: uc.Tab):
        responses: list[ResponseType] = []
        
        req_ids = set([request.request_id for request in self.requests])
        res_ids = set(self.responses)
        
        a = req_ids - res_ids
        b = res_ids - req_ids
        
        print(len(req_ids), len(res_ids), len(a), len(b))
        print(req_ids, res_ids)
        
        async with self.lock:
            for request in tqdm(self.requests):
                try:
                    if request.request.url.startswith('data:'):
                        print('data')
                    elif request.request_id in self.responses:
                        retries = 0
                        while retries < 50:
                            res = await page.send(cdp.network.get_response_body(request.request_id))
                            if res is not None:
                                break
                            retries = retries + 1
                        
                        if res is None:
                            continue
                        
                        # Prepare the response data
                        body = res[0]  # Response body
                        is_base64 = res[1]  # Whether the response is base64 encoded
                        responses.append({'request_id': request.request_id, 'body': body, 'is_base64': is_base64})
                    else:
                        print('wtf')

                except Exception as e:
                    print(f'Error getting body for request {request}: {e}')

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
    await tab.send(cdp.network.set_cache_disabled(True))
    
    input("press any key")

    # Change the URL based on use case
    start_time = time.time()
    tab = await browser.get('https://bing.com')
    
    print(await monitor.get_requests())
    print(await monitor.get_missing_responses())

    retries = 0
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Elapsed Time: {elapsed_time:.6f} seconds")
    while retries < 28:
        print(retries)
        if len(await monitor.get_missing_responses()) > 0:
            await tab.wait(t=0.5)
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f"Elapsed Time: {elapsed_time:.6f} seconds")
            print(await monitor.get_requests())
            retries = retries + 1
        else:
            break
    
    print("Awaiting Tab")
    await tab
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Elapsed Time: {elapsed_time:.6f} seconds")
    
    print(len(await monitor.receive(tab)))
    
    #with open('debug.txt', 'w') as f_obj:
    #    json.dump([RequestEncoder(request) for request in await monitor.get_missing_responses()], f_obj)
        #f_obj.write([RequestEncoder(request) for request in await monitor.get_missing_responses()])
    
    #time.sleep(1000)
    
    # Get the responses and process them
    #xhr_responses = await monitor.receive(tab)

if __name__ == '__main__':
    from encoders import RequestEncoder, ResponseEncoder
    uc.loop().run_until_complete(crawl())
