# backend/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import users, agents, analytics, campaigns, data

app = FastAPI(
    title="Agentic CRM Backend API",
    description="Unified API for Agentic CRM Dashboard and Agents",
    version="1.0.0",
)

# Development CORS (you said allow all for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
app.include_router(data.router, prefix="/data", tags=["Data"])


@app.get("/")
def root():
    return {"status": "ok", "message": "Agentic CRM Backend API running"}
