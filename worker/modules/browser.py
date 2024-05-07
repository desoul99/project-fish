from modules.helpers import RequestEncoder, ResponseEncoder
from nodriver import start, cdp
import pymongo
import uuid


class Browser():
    def __init__(self, config):
        self.mongo_client = pymongo.MongoClient(f'mongodb://{config["mongodb"]["username"]}:{config["mongodb"]["password"]}@{config["mongodb"]["host"]}:{config["mongodb"]["port"]}/', uuidRepresentation='standard')  
        self.mongo_db = self.mongo_client[config["mongodb"]["database"]]   
        self.mongo_collection = self.mongo_db[config["mongodb"]["collection"]]
        self.proxy = config["proxy"]['url']
        self.browser_executable_path = config['browser']['executable_path']
    
    async def start_browser(self):
        self.browser = await start(
            browser_args=[f"--proxy-server={self.proxy}", "--ignore-certificate-errors", '--test-type'],
            browser_executable_path=self.browser_executable_path,
        )
    
    async def main(self, url):
        scan_id = uuid.uuid4()
        requests = {'scan_id': scan_id, 'requests': [], 'hashes': []}

        async def receive_handler(event: cdp.network.ResponseReceived):
            response = ResponseEncoder(event)
            if not response['response']['url'].startswith('chrome') and response['response'].get('remoteIPAddress', False):
                res = next((req for req in requests['requests'] if req['request']['request_id'] == response['request_id']), None)
                if res:
                    index = requests['requests'].index(res)
                    requests['requests'][index]['response'] = response
                if response['response'].get('headers', False) and response['response']['headers'].get('pf_sha256', False):
                    requests['hashes'].append(response['response']['headers']['pf_sha256'])

        async def send_handler(event: cdp.network.RequestWillBeSent):
            request = RequestEncoder(event)
            initiator = request['initiator'].get('url', '') if request.get('initiator', False) else ''
            if not request['request']['url'].startswith('chrome') and not initiator.startswith('chrome'):
                requests['requests'].append({'request': request})

        tab = await self.browser.get('draft:,', new_window=True)

        await tab.send(cdp.network.set_cache_disabled(True))
        tab.add_handler(cdp.network.RequestWillBeSent, send_handler)
        tab.add_handler(cdp.network.ResponseReceived, receive_handler)

        await tab.get(url)

        retries = 0
        while retries < 7:  # implement request by tab id
            if sum(1 for dictionary in requests['requests'] if (len(dictionary) == 1) or (dictionary['request']['redirect_response'] is None)) > 0:
                await tab.wait(t=2)
                retries = retries + 1
        await tab

        self.mongo_collection.insert_one(requests)
        await tab.close()
