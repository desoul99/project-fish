import uuid
from typing import Any, Dict, Optional
from urllib.request import urlopen

from modules.requestMonitor import RequestMonitor, sha256_hash
from nodriver import cdp


class DataProcessor:
    """
    Handles transformation of raw request data to a format ready for database insertion.
    """

    @staticmethod
    def process_requests(scan_id: uuid.UUID, scan_url: str, request_monitor: RequestMonitor):
        """
        Process the raw requests data and return the database-ready requests transformed data.
        """
        requests = request_monitor.requests
        responses = request_monitor.responses
        paused_responses = request_monitor.paused_responses

        processed_data = {"scan_id": scan_id, "scan_url": scan_url, "final_url": "https://placeholder", "requests": [], "urls": [], "ips": [], "domains": [], "hashes": []}
        responses_content = []

        for _request in requests:
            if (_request.initiator.url is None or not _request.initiator.url.startswith("chrome")) and not _request.request.url.startswith("chrome"):
                request = request_encoder(_request)

                redirect = False
                for index, request_item in enumerate(processed_data["requests"]):
                    if request_item.get("request", {}).get("request_id") == _request.request_id:
                        redirect = True
                        if len(processed_data["requests"][index].get("requests", [])) == 0:
                            processed_data["requests"][index].setdefault("requests", []).append(processed_data["requests"][index]["request"])
                        processed_data["requests"][index]["requests"].append(request)
                        processed_data["requests"][index]["request"] = request
                        break

                if not redirect:
                    processed_data["requests"].append({"request": request})
                    index = processed_data["requests"].index({"request": request})

                    for _response in responses:
                        if _response.request_id == _request.request_id:
                            response = response_encoder(_response)
                            body = hash = None
                            if _response.response.url.startswith("data:"):
                                with urlopen(_response.response.url) as _:
                                    body = _.read()
                                    hash = sha256_hash(body)
                            else:
                                for _paused_response in paused_responses:
                                    if _paused_response["paused_response"].network_id == _request.request_id:
                                        body = _paused_response.get("body", None)
                                        hash = _paused_response.get("sha256_hash", None)
                                        break
                            if hash:
                                response["sha256_hash"] = hash
                                if hash not in processed_data["hashes"]:
                                    processed_data["hashes"].append(hash)
                                if body:
                                    responses_content.append({"sha256_hash": hash, "body": body})

                            processed_data["requests"][index]["response"] = response

        return processed_data, responses_content


def encode_event(evt, fields: Dict[str, str]) -> Dict[str, Optional[Any]]:
    encoded = {}
    for key, attr in fields.items():
        value = getattr(evt, attr, None)
        encoded[key] = value.to_json() if value is not None and hasattr(value, "to_json") else value
    return encoded


def request_encoder(evt: cdp.network.RequestWillBeSent) -> Dict[str, Optional[Any]]:
    fields = {"request": "request", "request_id": "request_id", "loader_id": "loader_id", "document_url": "document_url", "timestamp": "timestamp", "wall_time": "wall_time", "initiator": "initiator", "redirect_has_extra_info": "redirect_has_extra_info", "redirect_response": "redirect_response", "type": "type_", "frame_id": "frame_id", "has_user_gesture": "has_user_gesture"}
    return encode_event(evt, fields)


def response_encoder(evt: cdp.network.ResponseReceived) -> Dict[str, Optional[Any]]:
    fields = {"response": "response", "request_id": "request_id", "loader_id": "loader_id", "timestamp": "timestamp", "type": "type_", "has_extra_info": "has_extra_info", "frame_id": "frame_id"}
    return encode_event(evt, fields)
