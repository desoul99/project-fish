import json
import uuid
from typing import Any, Optional
from urllib.request import urlopen

from model.model import PausedResponseDict, ProcessedDataDict, ResponseContentDict
from modules.requestMonitor import RequestMonitor, sha256_hash
from nodriver import cdp
from nodriver.cdp.network import ResponseReceived


class DataProcessor:
    """
    Handles transformation of raw request data to a format ready for database insertion.
    """

    @staticmethod
    def format_requests(scan_id: uuid.UUID, scan_url: str, request_monitor: RequestMonitor) -> ProcessedDataDict:
        """
        Process the raw requests data and return the database-ready requests transformed data.
        """
        processed_data = ProcessedDataDict(scan_id=scan_id, scan_url=scan_url, final_url="", requests=[], urls=[], ips=[], domains=[], hashes=[])

        for _request in request_monitor.requests:
            if (_request.initiator.url is None or not _request.initiator.url.startswith("chrome")) and not _request.request.url.startswith("chrome"):
                request = request_encoder(_request)

                if _request.redirect_response:
                    if _request.redirect_response.security_details:
                        request["redirect_response"]["securityDetails"] = DataProcessor._calculate_certificate_hash(request["redirect_response"]["securityDetails"])

                    # Delete timing information to reduce the size of stored data
                    request["redirect_response"].pop("timing", None)

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

                    for _response in request_monitor.responses:
                        if _response.request_id == _request.request_id:
                            response = response_encoder(_response)
                            body, hash = DataProcessor._get_response_body_and_hash(_response, request_monitor.paused_responses)
                            if hash:
                                response["sha256_hash"] = hash
                                if hash not in processed_data["hashes"]:
                                    processed_data["hashes"].append(hash)

                            if _response.response.security_details:
                                response["response"]["securityDetails"] = DataProcessor._calculate_certificate_hash(response["response"]["securityDetails"])

                            # Delete timing information to reduce the size of stored data
                            response["response"].pop("timing", None)

                            processed_data["requests"][index]["response"] = response

        return processed_data

    @staticmethod
    def format_certificates(request_monitor: RequestMonitor) -> list[dict[str, Any]]:
        seen_hashes = set()
        certificates = []
        for request in request_monitor.requests:
            if request.redirect_response and request.redirect_response.security_details:
                encoded_request = request_encoder(request)
                sha256_security_details_hash = DataProcessor._calculate_certificate_hash(encoded_request["redirect_response"]["securityDetails"])
                if sha256_security_details_hash not in seen_hashes:
                    certificates.append({"sha256_securityDetails": sha256_security_details_hash, "securityDetails": DataProcessor._cleanup_security_details(encoded_request["redirect_response"]["securityDetails"])})
                    seen_hashes.add(sha256_security_details_hash)

        for response in request_monitor.responses:
            if response.response.security_details:
                encoded_response = response_encoder(response)
                sha256_security_details_hash = DataProcessor._calculate_certificate_hash(encoded_response["response"]["securityDetails"])
                if sha256_security_details_hash not in seen_hashes:
                    certificates.append({"sha256_securityDetails": sha256_security_details_hash, "securityDetails": DataProcessor._cleanup_security_details(encoded_response["response"]["securityDetails"])})
                    seen_hashes.add(sha256_security_details_hash)

        return certificates

    @staticmethod
    def _cleanup_security_details(security_details: dict) -> dict:
        # Removing browser-dependent fields
        security_details.pop("protocol", None)
        security_details.pop("certificateId", None)
        security_details.pop("keyExchange", None)
        security_details.pop("cipher", None)
        security_details.pop("keyExchangeGroup", None)
        security_details.pop("mac", None)
        security_details.pop("serverSignatureAlgorithm", None)
        security_details.pop("encryptedClientHello", None)
        return security_details

    @staticmethod
    def _calculate_certificate_hash(security_details: dict) -> str:
        return sha256_hash(json.dumps(DataProcessor._cleanup_security_details(security_details), sort_keys=True).encode("utf-8"))

    @staticmethod
    def format_content(request_monitor: RequestMonitor) -> list[ResponseContentDict]:
        responses_content: list[ResponseContentDict] = []

        for response in request_monitor.responses:
            body, hash = DataProcessor._get_response_body_and_hash(response, request_monitor.paused_responses)
            if hash and body:
                responses_content.append(ResponseContentDict(sha256_hash=hash, body=body))

        return responses_content

    @staticmethod
    def _get_response_body_and_hash(response: ResponseReceived, paused_responses: list[PausedResponseDict]) -> tuple[Optional[bytes], Optional[str]]:
        body = None
        hash = None

        if response.response.url.startswith("data:"):
            with urlopen(response.response.url) as _:
                body = _.read()
                hash = sha256_hash(body)
        else:
            for _paused_response in paused_responses:
                if _paused_response["paused_response"].network_id == response.request_id:
                    body = _paused_response.get("body", None)
                    hash = _paused_response.get("sha256_hash", None)
                    break

        return body, hash


def encode_event(evt, fields: dict[str, str]) -> dict[str, Optional[Any]]:
    encoded = {}
    for key, attr in fields.items():
        value = getattr(evt, attr, None)
        encoded[key] = value.to_json() if value is not None and hasattr(value, "to_json") else value
    return encoded


def request_encoder(evt: cdp.network.RequestWillBeSent) -> dict[str, Optional[Any]]:
    fields = {"request": "request", "request_id": "request_id", "loader_id": "loader_id", "document_url": "document_url", "timestamp": "timestamp", "wall_time": "wall_time", "initiator": "initiator", "redirect_has_extra_info": "redirect_has_extra_info", "redirect_response": "redirect_response", "type": "type_", "frame_id": "frame_id", "has_user_gesture": "has_user_gesture"}
    return encode_event(evt, fields)


def response_encoder(evt: cdp.network.ResponseReceived) -> dict[str, Optional[Any]]:
    fields = {"response": "response", "request_id": "request_id", "loader_id": "loader_id", "timestamp": "timestamp", "type": "type_", "has_extra_info": "has_extra_info", "frame_id": "frame_id"}
    return encode_event(evt, fields)
