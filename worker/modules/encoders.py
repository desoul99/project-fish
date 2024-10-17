import uuid
from nodriver import cdp
from typing import Optional, Dict, Any

from modules.requestMonitor import RequestMonitor


class DataProcessor:
    """
    Handles transformation of raw request data to a format ready for database insertion.
    """

    @staticmethod
    def process_requests(scan_id: uuid.UUID, request_monitor: RequestMonitor):
        """
        Process the raw requests data and return the database-ready transformed data.
        """
        requests = request_monitor.requests
        responses = request_monitor.responses
        paused_responses = request_monitor.paused_responses
        request_interception_mapping = request_monitor.request_interception_mapping

        processed_data = {"scan_id": scan_id, "scan_url": "https://placeholder", "final_url": "https://placeholder", "requests": [], "urls": [], "ips": [], "domains": [], "hashes": []}

        for _request in requests:
            request = RequestEncoder(_request)
            initiator = request["initiator"].get("url", "") if request.get("initiator", False) else ""
            if not request["request"]["url"].startswith("chrome") and not initiator.startswith("chrome"):
                processed_data["requests"].append({"request": request})

        for paused_response in paused_responses:
            for _req_id, _int_id in request_interception_mapping.items():
                if _int_id == paused_response["paused_response"].request_id:
                    request_id = _req_id
                    break

            _response = next((response for response in responses if response.request_id == request_id), None)
            if _response:
                response = ResponseEncoder(_response)

                hash = paused_response.get("sha256_hash")
                if hash:
                    response["hash"] = hash
                    processed_data["hashes"].append(hash)

                _req = next((req for req in processed_data["requests"] if req["request"]["request_id"] == response["request_id"]), None)
                index = processed_data["requests"].index(_req)
                if index:
                    processed_data["requests"][index]["response"] = response

        return processed_data

    @staticmethod
    def _format_timestamp(timestamp: str) -> str:
        """
        Private helper method to format timestamps.
        """
        # Implement any specific formatting logic, such as converting to a different format.
        # For simplicity, let's just return the original timestamp here.
        return timestamp


def encode_event(evt, fields: Dict[str, str]) -> Dict[str, Optional[Any]]:
    encoded = {}
    for key, attr in fields.items():
        value = getattr(evt, attr, None)
        encoded[key] = value.to_json() if value is not None and hasattr(value, "to_json") else value
    return encoded


def RequestEncoder(evt: cdp.network.RequestWillBeSent) -> Dict[str, Optional[Any]]:
    fields = {"request": "request", "request_id": "request_id", "loader_id": "loader_id", "document_url": "document_url", "timestamp": "timestamp", "wall_time": "wall_time", "initiator": "initiator", "redirect_has_extra_info": "redirect_has_extra_info", "redirect_response": "redirect_response", "type": "type_", "frame_id": "frame_id", "has_user_gesture": "has_user_gesture"}
    return encode_event(evt, fields)


def ResponseEncoder(evt: cdp.network.ResponseReceived) -> Dict[str, Optional[Any]]:
    fields = {"response": "response", "request_id": "request_id", "loader_id": "loader_id", "timestamp": "timestamp", "type": "type_", "has_extra_info": "has_extra_info", "frame_id": "frame_id"}
    return encode_event(evt, fields)
