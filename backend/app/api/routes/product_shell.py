"""Minimal sellable product shell: auth stub, plans, legal (EP8)."""
from __future__ import annotations

import hashlib
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/product-shell", tags=["product-shell"])

# In-memory stub store (replace with DB in production EP8 harden)
_USERS: dict[str, dict[str, Any]] = {}
_SESSIONS: dict[str, str] = {}  # token -> email

PLANS = {
    "free": {
        "id": "free",
        "name": "Free",
        "price_inr": 0,
        "entitlements": ["NIFTY_500", "practice", "guided"],
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price_inr": 999,
        "entitlements": ["NSE_ALL", "filters", "ai_copilot", "briefs", "practice", "history_90d"],
    },
}


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    plan: str = "free"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


@router.get("/plans")
async def list_plans() -> dict:
    return {"plans": list(PLANS.values()), "billing": "razorpay_stub"}


@router.post("/signup")
async def signup(payload: SignupRequest) -> dict:
    email = str(payload.email).lower()
    if email in _USERS:
        raise HTTPException(status_code=400, detail="Account already exists")
    plan = payload.plan if payload.plan in PLANS else "free"
    salt = secrets.token_hex(8)
    _USERS[email] = {
        "email": email,
        "salt": salt,
        "password_hash": _hash(payload.password, salt),
        "plan": plan,
        "broker_connected": False,
    }
    token = secrets.token_urlsafe(24)
    _SESSIONS[token] = email
    return {"token": token, "user": {"email": email, "plan": plan}, "claim": "Stub auth — replace with real IdP"}


@router.post("/login")
async def login(payload: LoginRequest) -> dict:
    email = str(payload.email).lower()
    user = _USERS.get(email)
    if not user or user["password_hash"] != _hash(payload.password, user["salt"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(24)
    _SESSIONS[token] = email
    return {"token": token, "user": {"email": email, "plan": user["plan"]}}


@router.get("/me")
async def me(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    email = _SESSIONS.get(token)
    if not email or email not in _USERS:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = _USERS[email]
    return {
        "email": email,
        "plan": user["plan"],
        "entitlements": PLANS[user["plan"]]["entitlements"],
        "broker_connected": user["broker_connected"],
    }


@router.post("/billing/razorpay/checkout-stub")
async def razorpay_checkout_stub(payload: dict) -> dict:
    plan = str(payload.get("plan") or "pro")
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    return {
        "provider": "razorpay",
        "status": "stub",
        "order_id": f"order_stub_{secrets.token_hex(6)}",
        "amount_paise": PLANS[plan]["price_inr"] * 100,
        "claim": "Checkout stub — wire Razorpay keys before charging customers",
    }


@router.post("/broker/connect-stub")
async def broker_connect_stub(authorization: str | None = Header(default=None)) -> dict:
    await me(authorization)
    return {
        "connected": False,
        "mode": "paper_only",
        "disclaimer": (
            "Broker connect is disclaimer-first. TradePilot never places unsupervised live orders. "
            "Practice remains fake money until you explicitly confirm each live arm."
        ),
    }


@router.get("/legal/disclosures")
async def legal_disclosures() -> dict:
    return {
        "risk": "Trading involves risk of loss. Past results do not guarantee future returns.",
        "paper": "Practice trades are fake money and are not brokerage orders.",
        "ai": "AI explains grounded engine facts only and never invents Entry, Stop, Target, or OR levels.",
        "assistant": "TradePilot is a trading assistant, not certified investment advice or an autonomous bot.",
    }


__all__ = ["router"]
