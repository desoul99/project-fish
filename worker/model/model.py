import re
import uuid
from dataclasses import dataclass, field
from typing import Optional, TypedDict, Any

from nodriver import cdp


@dataclass
class MongoDBConfig:
    username: str
    password: str
    host: str
    port: str
    database: str
    request_collection: str
    content_collection: str
    certificate_collection: str

    def get_connection_url(self) -> str:
        return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/"


@dataclass
class RabbitMQConfig:
    username: str
    password: str
    host: str
    port: str
    url_queue: str

    def get_connection_url(self) -> str:
        return f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/"


@dataclass
class MaxMindDBConfig:
    asn_database_path: str
    country_database_path: str


@dataclass
class EmulationConfig:
    emulation_config: str


@dataclass
class RedisConfig:
    host: str
    port: str
    content_database: str
    certificate_database: str

    def __post_init__(self) -> None:
        # Convert port to int after initialization
        self.port = int(self.port)
        self.content_database = int(self.content_database)
        self.certificate_database = int(self.certificate_database)


@dataclass
class BrowserConfig:
    max_tabs: int
    pageload_timeout: int
    browser_timeout: int
    min_request_wait: int
    max_content_size: str
    executable_path: Optional[str] = None
    proxy: Optional[str] = None
    execution_args: Optional[list[str]] = field(default_factory=list)

    # Define default flags as a class variable
    DEFAULT_EXECUTION_ARGS: list[str] = field(default_factory=lambda: ["--ignore-certificate-errors", "--test-type"])

    def __post_init__(self) -> None:
        combined_execution_args: set[str] = set(self.execution_args) | set(self.DEFAULT_EXECUTION_ARGS)

        # If proxy is set, automatically add the proxy flag
        if self.proxy:
            proxy_execution_arg: str = f"--proxy-server={self.proxy}"
            combined_execution_args.add(proxy_execution_arg)

        self.execution_args = list(combined_execution_args)

        self.max_content_size = self.max_content_size.strip().upper()
        match = re.match(r"^(\d+)(B|KB|MB)$", self.max_content_size)

        if not match:
            raise ValueError(f"Invalid size format: {self.max_content_size}, must be one of 'B', 'KB', 'MB")

        size, unit = match.groups()
        size = int(size)

        units = {
            "B": 1,
            "KB": 1024,
            "MB": 1024**2,
        }

        self.max_content_size = size * units[unit]


@dataclass
class Config:
    mongodb: MongoDBConfig
    rabbitmq: RabbitMQConfig
    browser: BrowserConfig
    redis: RedisConfig
    maxminddb: MaxMindDBConfig
    emulation: EmulationConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(mongodb=MongoDBConfig(**data["mongodb"]), rabbitmq=RabbitMQConfig(**data["rabbitmq"]), redis=RedisConfig(**data["redis"]), browser=BrowserConfig(**data["browser"]), maxminddb=MaxMindDBConfig(**data["maxminddb"]), emulation=EmulationConfig(**data["emulation"]))


@dataclass
class DeviceMetrics:
    width: int
    height: int
    device_scale_factor: float
    mobile: bool
    scale: Optional[float] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    dont_set_visible_size: bool = False
    screen_orientation: Optional[cdp.emulation.ScreenOrientation] = None
    viewport: Optional[cdp.page.Viewport] = None
    display_feature: Optional[cdp.emulation.DisplayFeature] = None
    device_posture: Optional[cdp.emulation.DevicePosture] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceMetrics":
        # Convert screen_orientation if provided in dict form
        if "screen_orientation" in data and isinstance(data["screen_orientation"], dict):
            data["screen_orientation"] = cdp.emulation.ScreenOrientation(**data["screen_orientation"])
        if "viewport" in data and isinstance(data["viewport"], dict):
            data["viewport"] = cdp.page.Viewport(**data["viewport"])
        if "display_feature" in data and isinstance(data["display_feature"], dict):
            data["viewport"] = cdp.emulation.DisplayFeature(**data["display_feature"])
        if "device_posture" in data and isinstance(data["device_posture"], dict):
            data["device_posture"] = cdp.emulation.DevicePosture(**data["device_posture"])
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
            "mobile": self.mobile,
            "scale": self.scale,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "dont_set_visible_size": self.dont_set_visible_size,
            "screen_orientation": self.screen_orientation,
            "viewport": self.viewport,
            "display_feature": self.display_feature,
            "device_posture": self.device_posture,
        }
        return data


@dataclass
class UserAgentOverride:
    user_agent: str
    accept_language: str
    platform: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserAgentOverride":
        return cls(**data)

    def to_dict(self) -> dict[str, str]:
        return {"user_agent": self.user_agent, "accept_language": self.accept_language, "platform": self.platform}


@dataclass
class EmulationDevice:
    name: str
    device_metrics: DeviceMetrics
    user_agent_override: UserAgentOverride
    is_mobile: bool
    accepted_encodings: Optional[list[cdp.network.ContentEncoding]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmulationDevice":
        # Process accepted_encodings list of dictionaries to cdp ContentEncoding objects
        if data.get("accepted_encodings", []):
            encodings = [cdp.network.ContentEncoding(value=enc["value"]) for enc in data.get("accepted_encodings", [])]
        else:
            encodings = None

        # Instantiate the main class using sub-dictionaries converted to their respective classes
        return cls(name=data["name"], device_metrics=DeviceMetrics.from_dict(data["device_metrics"]), user_agent_override=UserAgentOverride.from_dict(data["user_agent_override"]), is_mobile=data["is_mobile"], accepted_encodings=encodings)


@dataclass
class RabbitMQMessage:
    url: str
    emulation_device: Optional[EmulationDevice]
    proxy: Optional[str]
    page_cookies: Optional[list[cdp.network.CookieParam]]

    from modules.emulation import Emulation

    @classmethod
    def from_dict(cls, data: dict[str, Any], emulation: "Emulation") -> "RabbitMQMessage":
        url = data.get("url")
        emulation_device = data.get("emulation_device", None)
        proxy = data.get("proxy", None)
        page_cookies = data.get("page_cookies", None)

        if url is None:
            raise ValueError("The 'url' field is required and cannot be None.")

        if not url.startswith("http"):
            url = "https://" + url

        if emulation_device is not None:
            emulation_device = emulation.get_device_by_name(emulation_device)
            if emulation_device is None:
                raise ValueError("The specified emulation device is not configured")

        if page_cookies is not None:
            _page_cookies = []
            for cookie in page_cookies:
                _page_cookies.append(cdp.network.CookieParam.from_json(cookie))
            page_cookies = _page_cookies

        return cls(url=url, emulation_device=emulation_device, proxy=proxy, page_cookies=page_cookies)


class ResponseContentDict(TypedDict):
    sha256_hash: str
    body: bytes


class PausedResponseDict(TypedDict):
    paused_response: cdp.fetch.RequestPaused
    body: Optional[bytes]
    sha256_hash: Optional[str]


class ExtractedDataDict(TypedDict):
    urls: list[str]
    ips: list[str]
    domains: list[str]
    hashes: list[str]
    asns: list[str]
    servers: list[str]
    certificates: list[str]
    redirects: list[list[str]]
    cookies: list[dict]
    console_logs: list[dict]


class ScanInfoDict(TypedDict):
    url: str
    final_url: str
    domain: str
    asn: str
    ip: str
    certificate: str
    initial_frame: str
    screenshot_hash: Optional[str]
    # geo: TODO


class ProcessedDataDict(TypedDict):
    scan_id: uuid.UUID
    scan_info: Optional[ScanInfoDict]
    requests: list[dict]
    extracted_data: Optional[ExtractedDataDict]
