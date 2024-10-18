import pymongo.synchronous.collection
import pymongo.synchronous.database
import redis
from model import model


class Database:
    def __init__(self, config_mongo: model.MongoDBConfig, config_redis: model.RedisConfig) -> None:
        self.config_mongo: model.MongoDBConfig = config_mongo
        self.mongo_client = pymongo.MongoClient(self.config_mongo.get_connection_url(), uuidRepresentation="standard")
        self.mongo_db: pymongo.synchronous.database.Database = self.mongo_client[self.config_mongo.database]
        self.mongo_request_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config_mongo.request_collection]
        self.mongo_content_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config_mongo.content_collection]

        self.config_redis: model.RedisConfig = config_redis
        self.redis_client = redis.StrictRedis(host=self.config_redis.host, port=self.config_redis.port, db=self.config_redis.database)

    def insert_requests(self, data) -> None:
        self.mongo_request_collection.insert_one(data)

    def insert_content(self, data: list) -> None:
        for content in data:
            if not self.redis_client.exists(content["sha256_hash"]):
                self.mongo_content_collection.insert_one(content)
            self.redis_client.incr(content["sha256_hash"])
