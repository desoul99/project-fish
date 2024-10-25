import json
import uuid
from typing import Any, Optional
from urllib.request import urlopen

from model.model import PausedResponseDict, ProcessedDataDict, ResponseContentDict, ScanInfoDict, ExtractedDataDict, Config, MaxMindDBConfig
from modules.requestMonitor import RequestMonitor, sha256_hash
from nodriver import cdp
from nodriver.cdp.network import ResponseReceived

import maxminddb
import ipaddress
from urllib.parse import urlparse


class DataProcessor:
    """
    Handles transformation of raw request data to a format ready for database insertion.
    """

    @staticmethod
    def format_requests(scan_id: uuid.UUID, scan_url: str, request_monitor: RequestMonitor, config: Config) -> ProcessedDataDict:
        """
        Process the raw requests data and return the database-ready requests transformed data.
        """
        scan_info = ScanInfoDict(url=scan_url, final_url="", asn="", certificate="", domain="", ip="", initial_frame="")
        extracted_data = ExtractedDataDict(asns=[], domains=[], hashes=[], ips=[], servers=[], urls=[], certificates=[], cookies=[], console_logs=[])

        for _request in request_monitor.requests:
            if _request.frame_id:
                scan_info["initial_frame"] = _request.frame_id
                break

        processed_data = ProcessedDataDict(scan_id=scan_id, requests=[])

        for _request in request_monitor.requests:
            if (_request.initiator.url is None or not _request.initiator.url.startswith("chrome")) and not _request.request.url.startswith("chrome"):
                request = request_encoder(_request)

                if _request.redirect_response:
                    if _request.redirect_response.security_details:
                        request["redirect_response"]["securityDetails"] = DataProcessor._calculate_certificate_hash(request["redirect_response"]["securityDetails"])
                        extracted_data["certificates"].append(request["redirect_response"]["securityDetails"])

                    if _request.redirect_response.remote_ip_address:
                        _asn = DataProcessor._calculate_asn(_request.redirect_response.remote_ip_address, config.maxminddb)
                        request["redirect_response"]["asn"] = _asn

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
                        if (_response.request_id == _request.request_id) and (_response.response.status not in RequestMonitor.REDIRECT_STATUS_CODES):
                            response = response_encoder(_response)

                            if _response.response.remote_ip_address:
                                _asn = DataProcessor._calculate_asn(_response.response.remote_ip_address, config.maxminddb)
                                if _asn:
                                    response["asn"] = _asn

                            body, hash = DataProcessor._get_response_body_and_hash(_response, request_monitor.paused_responses)
                            if hash:
                                response["sha256_hash"] = hash
                                if hash not in extracted_data["hashes"]:
                                    extracted_data["hashes"].append(hash)

                            if _response.response.security_details:
                                response["response"]["securityDetails"] = DataProcessor._calculate_certificate_hash(response["response"]["securityDetails"])
                                extracted_data["certificates"].append(response["response"]["securityDetails"])

                            # Delete timing information to reduce the size of stored data
                            response["response"].pop("timing", None)

                            processed_data["requests"][index]["response"] = response

        extracted_data["ips"], extracted_data["urls"], extracted_data["servers"], extracted_data["asns"], extracted_data["domains"], extracted_data["cookies"], extracted_data["console_logs"] = DataProcessor._extract_data(request_monitor=request_monitor, config=config.maxminddb)
        extracted_data["certificates"] = list(set(extracted_data["certificates"]))

        # Sort requests list by timestamp
        processed_data["requests"].sort(key=lambda x: x["request"]["timestamp"])

        # Sort request redirect 'requests' list by timestamp
        for request_dict in processed_data["requests"]:
            if "requests" in request_dict.keys():
                request_dict["requests"].sort(key=lambda x: x["timestamp"])

        scan_info["final_url"] = scan_info["url"]
        redirects = []
        for r in processed_data["requests"]:
            if r["request"]["frame_id"] == scan_info["initial_frame"]:
                if (scan_info["final_url"] != r["request"]["document_url"]) or ((not scan_info["asn"] and not scan_info["certificate"] and not scan_info["ip"] and not scan_info["domain"]) and scan_info["final_url"] == r["request"]["document_url"]):
                    scan_info["final_url"] = r["request"]["document_url"]
                    if r["response"].get("asn", None):
                        scan_info["asn"] = r["response"]["asn"]
                        scan_info["ip"] = r["response"]["response"]["remoteIPAddress"]
                    if r["response"]["response"].get("securityDetails", None):
                        scan_info["certificate"] = r["response"]["response"]["securityDetails"]
                    try:
                        o = urlparse(scan_info["final_url"])
                        scan_info["domain"] = o.hostname
                    except ValueError:
                        continue

                if "requests" in r.keys():
                    _redirect_list = [redir["request"]["url"] for redir in r["requests"]]
                    if scan_info["final_url"] == _redirect_list[-1]:
                        redirects.append(_redirect_list)

        extracted_data["redirects"] = redirects

        processed_data["extracted_data"] = extracted_data
        processed_data["scan_info"] = scan_info

        return processed_data

    @staticmethod
    def _extract_data(request_monitor: RequestMonitor, config: MaxMindDBConfig) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str], list[str]]:
        ips = set()
        urls = set()
        servers = set()
        asns = set()
        domains = set()
        cookies = []
        console_logs = []
        for request in request_monitor.requests:
            if request.redirect_response:
                if request.redirect_response.remote_ip_address:
                    ips.add(request.redirect_response.remote_ip_address)

                for key, value in request.redirect_response.headers.items():
                    if key.lower() == "server":
                        servers.add(value)

                if not request.redirect_response.url.startswith("data:") and not request.redirect_response.url.startswith("blob:"):
                    urls.add(request.redirect_response.url)
            if not request.request.url.startswith("data:") and not request.request.url.startswith("blob:"):
                urls.add(request.request.url)

        for response in request_monitor.responses:
            if response.response.remote_ip_address:
                ips.add(response.response.remote_ip_address)

            if not response.response.url.startswith("data:") and not response.response.url.startswith("blob:"):
                urls.add(response.response.url)

            for key, value in response.response.headers.items():
                if key.lower() == "server":
                    servers.add(value)

        valid_ips = set()
        for ip in ips:
            try:
                ipaddress.ip_address(ip)
                valid_ips.add(ip)
            except ValueError:
                continue
        ips = valid_ips

        for ip in ips:
            asn_number = DataProcessor._calculate_asn(ip, config)
            if asn_number:
                asns.add(asn_number)

        for url in urls:
            try:
                o = urlparse(url)
                domains.add(o.hostname)
            except ValueError:
                continue

        for cookie in request_monitor.cookies:
            cookies.append(cookie.to_json())

        for console_log in request_monitor.console_logs:
            console_logs.append(console_log.to_json())

        return list(ips), list(urls), list(servers), list(asns), list(domains), cookies, console_logs

    @staticmethod
    def _calculate_asn(ip: str, config: MaxMindDBConfig) -> Optional[str]:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return None

        with maxminddb.open_database(config.asn_database_path) as asn_db:
            asn_info = asn_db.get(ip)
            if asn_info:
                asn_number = asn_info.get("autonomous_system_number", None)
                if asn_number:
                    return asn_number
        return None

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
                if (_paused_response["paused_response"].network_id == response.request_id) and (_paused_response["paused_response"].response_status_code == response.response.status):
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
