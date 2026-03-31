from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
import os
import smtplib
from email.message import EmailMessage
import math
import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, File, Form
from app.services.email_service import EmailService
from dotenv import load_dotenv

load_dotenv()

class StatusUpdate(BaseModel):
    status: str

app = FastAPI(title="Ritesh Rakshit Art Gallery API", version="1.0.0")
email_service = EmailService()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "art_gallery")
client = AsyncIOMotorClient(MONGO_URI)
db = client[MONGO_DB_NAME]

class CartItem(BaseModel):
    artwork_id: str
    quantity: int = 1

class Order(BaseModel):
    name: str
    email: str
    phone: str
    address: str
    city: str
    pincode: str
    items: List[CartItem]
    total: float

class ContactMessage(BaseModel):
    name: str
    email: str
    message: str

class OrderStatusUpdate(BaseModel):
    status: str

class SettingsUpdate(BaseModel):
    is_taking_orders: bool

class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class AdminLogin(BaseModel):
    password: str

class NewsletterSignup(BaseModel):
    email: str

SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

if CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "ritesh_art_vault_2024")

async def get_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized access",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    if token != ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
    
async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = authorization.split(" ")[1]
    user = await db.users.find_one({"email": token})
    if not user:
        # Fallback for session persistence if email is not used as token
        user = await db.users.find_one({"id": token})
        
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user


INITIAL_ARTWORKS =  [
    {"id":"cha-001","title":"Whispers of the Soul","category":"charcoal","medium":"Charcoal on Paper","price":8500,"original_price":10000,"size":"18\" × 24\"","description":"A deeply expressive charcoal portrait capturing raw human emotion.","available":True,"featured":True,"year":2024,"tags":["portrait","monochrome"],"image_url":"https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5?auto=format&fit=crop&q=80&w=1000"},
    {"id":"oil-001","title":"Golden Hour Reverie","category":"oil-painting","medium":"Oil on Canvas","price":24500,"original_price":28000,"size":"24\" × 36\"","description":"A luminous landscape bathed in the warm glow of golden hour.","available":True,"featured":True,"year":2024,"tags":["landscape","light"],"image_url":"https://images.unsplash.com/photo-1541963463532-d68292c34b19?auto=format&fit=crop&q=80&w=1000"},
    {"id":"psk-001","title":"The Chess Player","category":"pencil-sketch","medium":"Graphite on Bristol Board","price":4800,"original_price":None,"size":"12\" × 16\"","description":"A meticulous graphite portrait of a chess grandmaster mid-game.","available":True,"featured":False,"year":2024,"tags":["portrait","realism"],"image_url":"https://images.unsplash.com/photo-1513364776144-60967b0f800f?auto=format&fit=crop&q=80&w=1000"},
    {"id":"acp-001","title":"Neon Garden","category":"acrylic-painting","medium":"Acrylic on Canvas","price":15500,"original_price":None,"size":"20\" × 30\"","description":"A boldly contemporary acrylic piece where nature meets electric vibrancy.","available":True,"featured":True,"year":2024,"tags":["abstract","neon"],"image_url":"https://images.unsplash.com/photo-1549490349-8643362247b5?auto=format&fit=crop&q=80&w=1000"},
    {"id":"afp-001","title":"Mother — Fiber Portrait","category":"acrylic-fiber-portrait","medium":"Acrylic & Fiber on Board","price":35000,"original_price":40000,"size":"16\" × 20\"","description":"An extraordinary mixed-media portrait combining acrylic paint with hand-laid fiber.","available":True,"featured":True,"year":2024,"tags":["mixed-media","3D"],"image_url":"https://images.unsplash.com/photo-1578301978693-85fa9c0320b9?auto=format&fit=crop&q=80&w=1000"},
]

@app.on_event("startup")
async def startup_event():
    try:
        # Verify connection is alive
        await client.admin.command("ping")
        print(f"✅ Connected to MongoDB Atlas — DB: '{MONGO_DB_NAME}'")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return

    count = await db.artworks.count_documents({})
    print(f"📦 Artworks in DB: {count}")
    if count == 0:
        await db.artworks.insert_many([dict(a) for a in INITIAL_ARTWORKS])
        print("🌱 Seeded initial artworks")
        
    settings = await db.settings.find_one({"id": "global"})
    if not settings:
        await db.settings.insert_one({
            "id": "global",
            "is_taking_orders": True
        })

@app.on_event("shutdown")
async def shutdown_event():
    client.close()

@app.get("/")
def root():
    return {"message": "Ritesh Rakshit Art Gallery API", "version": "1.0.0"}

@app.get("/artworks")
async def get_artworks(category: Optional[str] = None, featured: Optional[bool] = None, available: Optional[bool] = None):
    query = {}
    if category:
        query["category"] = category
    if featured is not None:
        query["featured"] = featured
    if available is not None:
        query["available"] = available
        
    artworks = []
    cursor = db.artworks.find(query, {"_id": 0})
    async for document in cursor:
        artworks.append(document)
    return artworks

@app.get("/artworks/{artwork_id}")
async def get_artwork(artwork_id: str):
    art = await db.artworks.find_one({"id": artwork_id}, {"_id": 0})
    if not art:
        raise HTTPException(status_code=404, detail="Artwork not found")
    return art

@app.get("/categories")
async def get_categories():
    return [
        {"id": "charcoal", "name": "Charcoal", "icon": "pen-tool", "description": "Expressive charcoal works on paper"},
        {"id": "oil-painting", "name": "Oil Painting", "icon": "droplets", "description": "Classical and contemporary oil on canvas"},
        {"id": "pencil-sketch", "name": "Pencil Sketching", "icon": "pencil", "description": "Precise graphite and pencil artwork"},
        {"id": "acrylic-painting", "name": "Acrylic Painting", "icon": "palette", "description": "Vibrant acrylic on canvas"},
        {"id": "acrylic-fiber-portrait", "name": "Acrylic Fiber Portrait", "icon": "layers", "description": "Unique mixed-media fiber & acrylic portraits"},
    ]

@app.post("/orders", status_code=201)
async def create_order(order: Order, background_tasks: BackgroundTasks):
    settings = await db.settings.find_one({"id": "global"})
    if settings and not settings.get("is_taking_orders", True):
        raise HTTPException(status_code=400, detail="We are not currently accepting orders.")

    order_id = str(uuid.uuid4())[:8].upper()
    order_dict = order.dict()
    order_dict["id"] = order_id
    order_dict["status"] = "confirmed"
    await db.orders.insert_one(dict(order_dict))
    
    # [NEW] Automate "Sold" status for purchased artworks
    for item in order.items:
        await db.artworks.update_one({"id": item.artwork_id}, {"$set": {"available": False}})
    
    background_tasks.add_task(email_service.send_order_confirmation, order.email, order_id, order.name, order.total)
    
    return {"order_id": order_id, "status": "confirmed", "message": "Order placed! Ritesh will contact you within 24 hours."}

@app.post("/contact", status_code=201)
async def send_message(msg: ContactMessage):
    await db.messages.insert_one(msg.dict())
    return {"message": "Thank you! Ritesh will respond within 48 hours."}

@app.post("/auth/signup")
async def signup(user: UserCreate, background_tasks: BackgroundTasks):
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_dict = user.dict()
    user_dict["id"] = str(uuid.uuid4())
    await db.users.insert_one(user_dict)
    
    background_tasks.add_task(email_service.send_welcome_email, user.email, user.name)
    
    return {"message": "Account created successfully", "user_id": user_dict["id"], "name": user.name}

@app.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email, "password": credentials.password})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Logged in successfully", "user_id": user["id"], "name": user["name"], "email": user["email"]}
@app.post("/newsletter", status_code=201)
async def newsletter_signup(signup: NewsletterSignup, background_tasks: BackgroundTasks):
    await db.newsletter.update_one({"email": signup.email}, {"$set": {"email": signup.email}}, upsert=True)
    background_tasks.add_task(email_service.send_newsletter_confirmation, signup.email)
    return {"message": "Subscribed successfully"}

@app.get("/user/orders")
async def get_user_orders(user: dict = Depends(get_current_user)):
    user_email = user["email"]
    cursor = db.orders.find({"email": user_email}, {"_id": 0}).sort("_id", -1)
    orders = []
    async for doc in cursor:
        orders.append(doc)
    return orders

@app.get("/stats")
async def get_stats():
    total = await db.artworks.count_documents({})
    available = await db.artworks.count_documents({"available": True})
    sold = total - available
    
    # Fetch unique categories from current artworks
    categories_list = await db.artworks.distinct("category")
    
    # Fetch unique emails from orders to see "unique collectors"
    collectors = await db.orders.distinct("email")
    
    return {
        "total_artworks": total, 
        "available": available, 
        "sold": sold, 
        "categories": len(categories_list), 
        "years_experience": 12, # Static artist bio info
        "exhibitions": 28,      # Static artist bio info
        "collectors": len(collectors)
    }

@app.get("/settings")
async def get_settings():
    settings = await db.settings.find_one({"id": "global"}, {"_id": 0})
    if not settings:
        return {"is_taking_orders": True}
    return settings

@app.post("/admin/login")
async def admin_login(creds: AdminLogin):
    if creds.password == ADMIN_SECRET:
        return {"token": ADMIN_SECRET, "message": "Authenticated"}
    raise HTTPException(status_code=401, detail="Invalid admin password")

@app.put("/admin/settings")
async def update_settings(update: SettingsUpdate, admin: bool = Depends(get_admin)):
    await db.settings.update_one(
        {"id": "global"},
        {"$set": {"is_taking_orders": update.is_taking_orders}},
        upsert=True
    )
    return {"message": "Settings updated"}

@app.get("/admin/orders")
async def get_orders(page: int = 1, limit: int = 10, admin: bool = Depends(get_admin)):
    skip = (page - 1) * limit
    cursor = db.orders.find({}, {"_id": 0}).sort("_id", -1).skip(skip).limit(limit)
    orders = []
    async for doc in cursor:
        orders.append(doc)
    
    total = await db.orders.count_documents({})
    return {
        "orders": orders,
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 1
    }

@app.put("/admin/orders/{order_id}")
async def update_order_status(order_id: str, data: StatusUpdate, background_tasks: BackgroundTasks, admin: bool = Depends(get_admin)):
    # 1. Fetch current order to get user's email and name
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # [NEW] Status transition validation
    current_status = order.get("status", "confirmed").lower()
    new_status = data.status.lower()
    
    # Rule: Once shipped, cannot go back to confirmed/processing. Only delivered or cancelled.
    if current_status in ["shipped", "delivered", "cancelled"]:
        if new_status in ["confirmed", "processing"]:
            raise HTTPException(status_code=400, detail=f"Cannot move order back to '{new_status}' once it has been '{current_status}'.")
    
    if current_status in ["delivered", "cancelled"]:
        raise HTTPException(status_code=400, detail="Cannot change status of a completed/cancelled order.")
    
    # 2. Update status in database
    res = await db.orders.update_one({"id": order_id}, {"$set": {"status": data.status}})
    
    # 3. Queue an automated status update email
    background_tasks.add_task(
        email_service.send_status_update, 
        order["email"], 
        order_id, 
        order.get("name", "Collector"), 
        data.status
    )
    
    return {"message": f"Order status set to {data.status} and email sent to {order['email']}"}

@app.post("/admin/artworks", status_code=201)
async def add_artwork(
    title: str = Form(...),
    category: str = Form(...),
    medium: str = Form(...),
    price: float = Form(...),
    size: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(...),
    admin: bool = Depends(get_admin)
):
    if not CLOUDINARY_CLOUD_NAME:
        raise HTTPException(status_code=500, detail="Cloudinary is not configured. Please add keys to .env")
        
    try:
        # Use image.file directly for streaming upload
        result = cloudinary.uploader.upload(
            image.file,
            folder="art_gallery",
            resource_type="auto"
        )
        image_url = result.get("secure_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
        
    artwork_id = f"art-{str(uuid.uuid4())[:8].lower()}"
    
    new_artwork = {
        "id": artwork_id,
        "title": title,
        "category": category,
        "medium": medium,
        "price": price,
        "original_price": None,
        "size": size,
        "description": description,
        "available": True,
        "featured": True,
        "year": 2024,
        "tags": [category],
        "image_url": image_url
    }
    
    await db.artworks.insert_one(new_artwork)
    return {"message": "Artwork successfully uploaded!", "artwork": {"id": artwork_id, "image_url": image_url}}

@app.delete("/admin/artworks/{artwork_id}")
async def delete_artwork(artwork_id: str, admin: bool = Depends(get_admin)):
    result = await db.artworks.delete_one({"id": artwork_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Artwork not found")
    return {"message": "Artwork deleted successfully"}


@app.put("/admin/artworks/{artwork_id}/availability")
async def update_artwork_availability(artwork_id: str, data: AvailabilityUpdate = Body(...), admin: bool = Depends(get_admin)):
    # Search by both custom 'id' and MongoDB '_id' for robustness
    query = {"$or": [{"id": artwork_id}]}
    try:
         # Try to see if it qualifies as an ObjectId
         if len(artwork_id) == 24:
             query["$or"].append({"_id": ObjectId(artwork_id)})
    except: pass
    
    result = await db.artworks.update_one(query, {"$set": {"available": data.available}})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Artwork with ID {artwork_id} not found in database")
    return {"message": f"Artwork marked as {'available' if data.available else 'sold'}"}
