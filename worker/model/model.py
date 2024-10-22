import re
import uuid
from dataclasses import dataclass, field
from typing import Optional, TypedDict

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

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(mongodb=MongoDBConfig(**data["mongodb"]), rabbitmq=RabbitMQConfig(**data["rabbitmq"]), redis=RedisConfig(**data["redis"]), browser=BrowserConfig(**data["browser"]))


class ResponseContentDict(TypedDict):
    sha256_hash: str
    body: bytes


class PausedResponseDict(TypedDict):
    paused_response: cdp.fetch.RequestPaused
    body: Optional[bytes]
    sha256_hash: Optional[str]


class ProcessedDataDict(TypedDict):
    scan_id: uuid.UUID
    scan_url: str
    final_url: str
    requests: list[dict]
    urls: list[str]
    ips: list[str]
    domains: list[str]
    hashes: list[str]
