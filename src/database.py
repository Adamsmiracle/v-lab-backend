"""
Database configuration and connection management for the V-Lab backend using MongoDB.
"""
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
import logging

# Load environment variables (override existing ones)
load_dotenv(override=True)

# Setup logging
logger = logging.getLogger(__name__)

# MongoDB Configuration for Atlas
MONGODB_URL = os.getenv(
    "MONGODB_URL", 
    "mongodb+srv://username:password@cluster.mongodb.net/v_lab?retryWrites=true&w=majority"
)
DATABASE_NAME = os.getenv("DATABASE_NAME", "v_lab")

class MongoDB:
    """MongoDB connection manager"""
    client: AsyncIOMotorClient = None
    database = None

# MongoDB instance
mongodb = MongoDB()

async def connect_to_mongo():
    """Create database connection"""
    try:
        # Try multiple connection strategies for MongoDB Atlas
        connection_configs = [
            {
                "tls": True,
                "tlsAllowInvalidCertificates": False,
                "serverSelectionTimeoutMS": 5000,
                "connectTimeoutMS": 5000,
                "socketTimeoutMS": 5000
            },
            {
                "ssl": True,
                "ssl_cert_reqs": 0,  # ssl.CERT_NONE
                "serverSelectionTimeoutMS": 5000,
                "connectTimeoutMS": 5000,
                "socketTimeoutMS": 5000
            },
            {
                # Minimal config - let pymongo handle SSL
                "serverSelectionTimeoutMS": 5000,
                "connectTimeoutMS": 5000,
                "socketTimeoutMS": 5000
            }
        ]
        
        for i, config in enumerate(connection_configs):
            try:
                logger.info(f"🔄 Attempting MongoDB connection strategy {i+1}/3...")
                mongodb.client = AsyncIOMotorClient(MONGODB_URL, **config)
                mongodb.database = mongodb.client[DATABASE_NAME]
                
                # Test the connection
                await mongodb.client.admin.command('ping')
                logger.info(f"✅ Connected to MongoDB (strategy {i+1}) at {MONGODB_URL[:50]}...")
                return  # Success, exit the function
                
            except Exception as e:
                logger.warning(f"⚠️  Strategy {i+1} failed: {e}")
                if mongodb.client:
                    mongodb.client.close()
                    mongodb.client = None
                    mongodb.database = None
                continue
        
        # All strategies failed
        logger.warning("⚠️  All MongoDB connection strategies failed")
        logger.warning("🔄 Server will start without database (authentication disabled)")
        
    except Exception as e:
        logger.warning(f"⚠️  Failed to connect to MongoDB: {e}")
        logger.warning("🔄 Server will start without database (authentication disabled)")
        # Don't raise the exception - allow server to start
        mongodb.client = None
        mongodb.database = None

async def close_mongo_connection():
    """Close database connection"""
    if mongodb.client:
        mongodb.client.close()
        logger.info("Disconnected from MongoDB")

def get_database():
    """Get the MongoDB database instance"""
    return mongodb.database

# Collection names
USERS_COLLECTION = "users"
CIRCUITS_COLLECTION = "circuits"
SIMULATIONS_COLLECTION = "simulations"
SESSIONS_COLLECTION = "sessions"
