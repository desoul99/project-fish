from mitmproxy import http
import hashlib


class Addon:
    def response(self, flow: http.HTTPFlow):
        if flow.response.content:
            hash = hashlib.sha256(flow.response.content).hexdigest()
            flow.response.headers["pf_sha256"] = hash
        
addons = [Addon()]
