import uuid
from nodriver import cdp
from typing import Optional, Dict, Any

from modules.requestMonitor import PausedResponse


class DataProcessor:
    """
    Handles transformation of raw request data to a format ready for database insertion.
    """

    @staticmethod
    def process_requests(scan_id: uuid.UUID, requests: list[cdp.network.RequestWillBeSent], responses: list[cdp.network.ResponseReceived], paused_responses: list[PausedResponse]):
        """
        Process the raw requests data and return the database-ready transformed data.
        """
        processed_data = {"scan_id": scan_id, "scan_url": "https://placeholder", "final_url": "https://placeholder", "requests": [], "urls": [], "ips": [], "domains": [], "hashes": []}

        for req_evt in requests:
            request = RequestEncoder(req_evt)
            initiator = request["initiator"].get("url", "") if request.get("initiator", False) else ""
            if not request["request"]["url"].startswith("chrome") and not initiator.startswith("chrome"):
                processed_data["requests"].append({"request": request})

        print(len(paused_responses))
        for paused_response in paused_responses:
            for request in requests:
                if paused_response["paused_response"].request == request.request:
                    print(request.request_id)

        # for request in raw_requests:
        #     # Example transformation (cleaning, formatting, etc.)
        #     processed_request = {
        #         "url": request.get("url"),
        #         "status_code": request.get("status"),
        #         "headers": request.get("headers"),
        #         "timestamp": DataProcessor._format_timestamp(request.get("timestamp")),
        #         # Add other necessary transformations as needed.
        #     }
        #     processed_data.append(processed_request)

        return True

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
