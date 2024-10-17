from model import model

import pymongo.synchronous.collection
import pymongo.synchronous.database


class Database:
    def __init__(self, config: model.MongoDBConfig) -> None:
        self.config: model.MongoDBConfig = config
        self.mongo_client = pymongo.MongoClient(self.config.get_connection_url(), uuidRepresentation="standard")
        self.mongo_db: pymongo.synchronous.database.Database = self.mongo_client[self.config.database]
        self.mongo_collection: pymongo.synchronous.collection.Collection = self.mongo_db[self.config.collection]

    def insert(self, data) -> None:
        self.mongo_collection.insert_one(data)
