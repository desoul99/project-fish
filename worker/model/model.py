from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MongoDBConfig:
    username: str
    password: str
    host: str
    port: str
    database: str
    collection: str

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
class BrowserConfig:
    max_tabs: int
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


@dataclass
class Config:
    mongodb: MongoDBConfig
    rabbitmq: RabbitMQConfig
    browser: BrowserConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(mongodb=MongoDBConfig(**data["mongodb"]), rabbitmq=RabbitMQConfig(**data["rabbitmq"]), browser=BrowserConfig(**data["browser"]))
