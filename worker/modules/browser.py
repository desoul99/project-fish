from modules.encoders import RequestEncoder, ResponseEncoder
from modules import requestMonitor
from nodriver import start, cdp, loop
import requests
import pymongo
import asyncio
import yaml
import uuid
import json


class Browser():
    def __init__(self, config):
        self.mongo_client = pymongo.MongoClient(f'mongodb://{config["mongodb"]["username"]}:{config["mongodb"]["password"]}@{config["mongodb"]["host"]}:{config["mongodb"]["port"]}/', uuidRepresentation='standard')  
        self.mongo_db = self.mongo_client[config["mongodb"]["database"]]   
        self.mongo_collection = self.mongo_db[config["mongodb"]["collection"]]
        self.proxy = config["proxy"]['url']
        self.scan_id = uuid.uuid4()
        self.requests = {
            'scan_id': self.scan_id,
            'requests': [],
            'hashes': []
        }
        loop().run_until_complete(self.start_browser())
    
    async def start_browser(self):
        self.browser = await start(
            browser_args=[f"--proxy-server={self.proxy}", "--ignore-certificate-errors", '--test-type'], 
        )
        
    def load(self, url):
        if not url.startswith('http'):
            url = 'https://' + url
        
        loop().run_until_complete(self.main(url))
    
    async def main(self, url):
        self.main_tab = self.browser.main_tab
        await self.main_tab.send(cdp.network.set_cache_disabled(True))
        self.main_tab.add_handler(cdp.network.RequestWillBeSent, self.send_handler)
        self.main_tab.add_handler(cdp.network.ResponseReceived, self.receive_handler)
        page = await self.browser.get(url)
        retries = 0
        while retries < 7:
            if sum(1 for dictionary in self.requests['requests'] if (len(dictionary) == 1) or (dictionary['request']['redirect_response'] is None) ) > 0:
                await page.wait(t=2)
                retries = retries + 1
        await page
        self.mongo_collection.insert_one(self.requests)
        self.browser.stop()
        
    
    
    async def receive_handler(self, event: cdp.network.ResponseReceived):
        response = ResponseEncoder(event)
        if not response['response']['url'].startswith('chrome') and response['response'].get('remoteIPAddress', False):
            res = next((req for req in self.requests['requests'] if req['request']['request_id'] == response['request_id']), None)
            if res:
                index = self.requests['requests'].index(res)
                self.requests['requests'][index]['response'] = response
            if response['response'].get('headers', False) and response['response']['headers'].get('pf_sha256', False):
                self.requests['hashes'].append(response['response']['headers']['pf_sha256'])


    async def send_handler(self, event: cdp.network.RequestWillBeSent):
        request = RequestEncoder(event)
        initiator = request['initiator'].get('url', '') if request.get('initiator', False) else ''
        if not request['request']['url'].startswith('chrome') and not initiator.startswith('chrome'):
            self.requests['requests'].append({'request': request})
