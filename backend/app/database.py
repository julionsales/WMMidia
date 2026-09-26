import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "veif_veals")

client = AsyncIOMotorClient(MONGO_URI)
db = client[MONGO_DB]
users_collection = db["users"]
