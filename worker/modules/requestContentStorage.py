import logging
from typing import Optional

import pymongo.synchronous.collection
import pymongo.synchronous.database
import pymongo.database
import redis
from model import model


class RequestContentStorage:
    def __init__(self, config_mongo: model.MongoDBConfig, config_redis: model.RedisConfig) -> None:
        self.config_mongo: model.MongoDBConfig = config_mongo
        self.config_redis: model.RedisConfig = config_redis

        self.mongo_client: Optional[pymongo.MongoClient] = None
        self.mongo_db: Optional[pymongo.database.Database] = None
        self.redis_client: Optional[redis.StrictRedis] = None

    def __enter__(self) -> "RequestContentStorage":
        """Open connections to MongoDB and Redis."""
        try:
            self.mongo_client = pymongo.MongoClient(self.config_mongo.get_connection_url(), uuidRepresentation="standard")
            self.mongo_db: pymongo.synchronous.database.Database = self.mongo_client[self.config_mongo.database]
            self.mongo_request_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config_mongo.request_collection]
            self.mongo_content_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config_mongo.content_collection]

            # Define index on mongo_content_collection for sha256 hash
            self.mongo_content_collection.create_index([("sha256_hash", 1)], unique=True)

            self.redis_client = redis.StrictRedis(host=self.config_redis.host, port=self.config_redis.port, db=self.config_redis.database)
        except (pymongo.errors.ConnectionError, redis.ConnectionError) as e:
            logging.error("Failed to connect to the database: %s", e)
            raise  # Re-raise the exception to notify the caller.
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Close connections to MongoDB and Redis."""
        try:
            self.close()
        except Exception as e:
            logging.error("Error occurred while closing database connections: %s", e)
            raise

    def close(self) -> None:
        """Close the database connections."""
        if self.mongo_client:
            try:
                self.mongo_client.close()
            except Exception as e:
                logging.error("Error closing MongoDB client: %s", e)
                raise

        if self.redis_client:
            try:
                self.redis_client.close()
            except Exception as e:
                logging.error("Error closing Redis client: %s", e)
                raise

    def insert_requests(self, data: model.ProcessedDataDict) -> None:
        try:
            self.mongo_request_collection.insert_one(data)
        except Exception as e:
            logging.error("Error inserting request data: %s", e)
            raise  # Re-raise to notify the caller.

    def insert_content(self, data: list[model.ResponseContentDict]) -> None:
        for content in data:
            try:
                if not self.redis_client.exists(content["sha256_hash"]):
                    self.mongo_content_collection.insert_one(content)
                self.redis_client.incr(content["sha256_hash"])
            except Exception as e:
                logging.error("Error inserting content data: %s", e)
                raise  # Re-raise to notify the caller.
