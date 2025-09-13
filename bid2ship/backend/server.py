from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import hashlib
import secrets
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="Bid2Ship API", description="Reverse auction marketplace for logistics")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBasic()

# Enums
class UserRole(str, Enum):
    shipper = "shipper"
    driver = "driver"

class ShipmentStatus(str, Enum):
    posted = "posted"
    bidding_closed = "bidding_closed"
    in_transit = "in_transit"
    delivered = "delivered"

class BidStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str
    phone: str
    role: UserRole
    company_name: Optional[str] = None
    password_hash: Optional[str] = None  # Added for authentication
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: str
    role: UserRole
    company_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    phone: str
    role: UserRole
    company_name: Optional[str] = None
    created_at: datetime

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Shipment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    shipper_id: str
    origin_city: str
    destination_city: str
    description: str
    weight: float  # in tons
    deadline: datetime
    price_range: Optional[str] = None
    status: ShipmentStatus = ShipmentStatus.posted
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ShipmentCreate(BaseModel):
    origin_city: str
    destination_city: str
    description: str
    weight: float
    deadline: datetime
    price_range: Optional[str] = None

class Bid(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_id: str
    shipment_id: str
    amount: float
    message: Optional[str] = None
    status: BidStatus = BidStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BidCreate(BaseModel):
    shipment_id: str
    amount: float
    message: Optional[str] = None

class ShipmentWithBids(BaseModel):
    shipment: Shipment
    bids: List[Bid]
    bid_count: int

# Helper functions
def hash_password(password: str) -> str:
    """Hash password with salt"""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hashed.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    try:
        salt, hash_hex = hashed.split(':')
        expected_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return hash_hex == expected_hash.hex()
    except:
        return False

def prepare_for_mongo(data):
    """Convert datetime objects to ISO strings for MongoDB storage"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
    return data

def parse_from_mongo(item):
    """Convert ISO strings back to datetime objects"""
    if isinstance(item, dict):
        for key, value in item.items():
            if key in ['created_at', 'deadline'] and isinstance(value, str):
                try:
                    item[key] = datetime.fromisoformat(value)
                except:
                    pass
    return item

# Authentication
async def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> User:
    """Get current authenticated user"""
    user_data = await db.users.find_one({"email": credentials.username})
    if not user_data or not verify_password(credentials.password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_data = parse_from_mongo(user_data)
    return User(**user_data)

# Routes
@api_router.get("/")
async def root():
    return {"message": "Bid2Ship API - Reverse auction marketplace for logistics"}

# User Management
@api_router.post("/users/register", response_model=UserResponse)
async def register_user(user_data: UserCreate):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user with hashed password
    user_dict = user_data.dict()
    password = user_dict.pop("password")
    user_dict["password_hash"] = hash_password(password)
    
    user_obj = User(**user_dict)
    user_mongo = prepare_for_mongo(user_obj.dict())
    
    await db.users.insert_one(user_mongo)
    
    # Return user without password hash
    return UserResponse(**{k: v for k, v in user_obj.dict().items() if k != 'password_hash'})

@api_router.post("/users/login")
async def login_user(login_data: UserLogin):
    user_data = await db.users.find_one({"email": login_data.email})
    if not user_data or not verify_password(login_data.password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_data = parse_from_mongo(user_data)
    user = User(**user_data)
    user_response = UserResponse(**{k: v for k, v in user.dict().items() if k != 'password_hash'})
    return {"message": "Login successful", "user": user_response}

@api_router.get("/users/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(**{k: v for k, v in current_user.dict().items() if k != 'password_hash'})

# Shipment Management
@api_router.post("/shipments", response_model=Shipment)
async def create_shipment(shipment_data: ShipmentCreate, current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.shipper:
        raise HTTPException(status_code=403, detail="Only shippers can create shipments")
    
    shipment_dict = shipment_data.dict()
    shipment_dict["shipper_id"] = current_user.id
    
    shipment_obj = Shipment(**shipment_dict)
    shipment_mongo = prepare_for_mongo(shipment_obj.dict())
    
    await db.shipments.insert_one(shipment_mongo)
    return shipment_obj

@api_router.get("/shipments", response_model=List[Shipment])
async def get_shipments(status: Optional[ShipmentStatus] = None):
    query = {}
    if status:
        query["status"] = status
    
    shipments = await db.shipments.find(query).sort("created_at", -1).to_list(100)
    return [Shipment(**parse_from_mongo(shipment)) for shipment in shipments]

@api_router.get("/shipments/my", response_model=List[ShipmentWithBids])
async def get_my_shipments(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.shipper:
        raise HTTPException(status_code=403, detail="Only shippers can view their shipments")
    
    shipments = await db.shipments.find({"shipper_id": current_user.id}).sort("created_at", -1).to_list(100)
    
    result = []
    for shipment_data in shipments:
        shipment = Shipment(**parse_from_mongo(shipment_data))
        
        # Get bids for this shipment
        bids_data = await db.bids.find({"shipment_id": shipment.id}).sort("amount", 1).to_list(100)
        bids = [Bid(**parse_from_mongo(bid)) for bid in bids_data]
        
        result.append(ShipmentWithBids(
            shipment=shipment,
            bids=bids,
            bid_count=len(bids)
        ))
    
    return result

@api_router.get("/shipments/{shipment_id}", response_model=ShipmentWithBids)
async def get_shipment(shipment_id: str):
    shipment_data = await db.shipments.find_one({"id": shipment_id})
    if not shipment_data:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    shipment = Shipment(**parse_from_mongo(shipment_data))
    
    # Get bids for this shipment
    bids_data = await db.bids.find({"shipment_id": shipment_id}).sort("amount", 1).to_list(100)
    bids = [Bid(**parse_from_mongo(bid)) for bid in bids_data]
    
    return ShipmentWithBids(
        shipment=shipment,
        bids=bids,
        bid_count=len(bids)
    )

# Bidding System
@api_router.post("/bids", response_model=Bid)
async def create_bid(bid_data: BidCreate, current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.driver:
        raise HTTPException(status_code=403, detail="Only drivers can place bids")
    
    # Check if shipment exists and is still open for bidding
    shipment_data = await db.shipments.find_one({"id": bid_data.shipment_id})
    if not shipment_data:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    if shipment_data["status"] != ShipmentStatus.posted:
        raise HTTPException(status_code=400, detail="Shipment is not open for bidding")
    
    # Check if driver already has a bid on this shipment
    existing_bid = await db.bids.find_one({
        "driver_id": current_user.id,
        "shipment_id": bid_data.shipment_id
    })
    if existing_bid:
        raise HTTPException(status_code=400, detail="You have already placed a bid on this shipment")
    
    bid_dict = bid_data.dict()
    bid_dict["driver_id"] = current_user.id
    
    bid_obj = Bid(**bid_dict)
    bid_mongo = prepare_for_mongo(bid_obj.dict())
    
    await db.bids.insert_one(bid_mongo)
    return bid_obj

@api_router.get("/bids/my", response_model=List[Bid])
async def get_my_bids(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.driver:
        raise HTTPException(status_code=403, detail="Only drivers can view their bids")
    
    bids_data = await db.bids.find({"driver_id": current_user.id}).sort("created_at", -1).to_list(100)
    return [Bid(**parse_from_mongo(bid)) for bid in bids_data]

@api_router.put("/bids/{bid_id}/accept")
async def accept_bid(bid_id: str, current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.shipper:
        raise HTTPException(status_code=403, detail="Only shippers can accept bids")
    
    # Get the bid
    bid_data = await db.bids.find_one({"id": bid_id})
    if not bid_data:
        raise HTTPException(status_code=404, detail="Bid not found")
    
    # Verify the shipment belongs to current user
    shipment_data = await db.shipments.find_one({"id": bid_data["shipment_id"]})
    if not shipment_data or shipment_data["shipper_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="You can only accept bids on your own shipments")
    
    # Accept the bid and reject others
    await db.bids.update_one({"id": bid_id}, {"$set": {"status": BidStatus.accepted}})
    await db.bids.update_many(
        {"shipment_id": bid_data["shipment_id"], "id": {"$ne": bid_id}},
        {"$set": {"status": BidStatus.rejected}}
    )
    
    # Update shipment status
    await db.shipments.update_one(
        {"id": bid_data["shipment_id"]},
        {"$set": {"status": ShipmentStatus.bidding_closed}}
    )
    
    return {"message": "Bid accepted successfully"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()