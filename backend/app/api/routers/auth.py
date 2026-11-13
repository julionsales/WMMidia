from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import current_user, get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutil import utcnow
from app.models.common import serialize
from app.models.schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["Autenticação"])

# Hash fixo para igualar o tempo de resposta quando o e-mail não existe.
_DUMMY_HASH = hash_password("senha-ficticia-apenas-para-tempo-constante")


async def _throttle(request: Request, email: str) -> str:
    settings = get_settings()
    client_ip = request.client.host if request.client else "?"
    key = "login:" + hashlib.sha256(f"{client_ip}|{email}".encode()).hexdigest()[:32]
    redis = request.app.state.redis
    attempts = await redis.incr(key)
    if attempts == 1:
        await redis.expire(key, settings.login_window_seconds)
    if attempts > settings.login_max_attempts:
        raise HTTPException(429, "Muitas tentativas de login. Aguarde alguns minutos.")
    return key


@router.post("/login")
async def login(payload: LoginIn, request: Request, db: AsyncDatabase = Depends(get_db)):
    email = payload.email.lower()
    key = await _throttle(request, email)
    user = await db.users.find_one({"email": email, "active": True})
    valid = verify_password(payload.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, "E-mail ou senha inválidos")
    await request.app.state.redis.delete(key)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": utcnow()}})
    return {
        "access_token": create_access_token(email),
        "token_type": "bearer",
        "user": serialize({"id": user["_id"], "email": email, "name": user.get("name"), "role": user.get("role")}),
    }


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return serialize({"id": user["_id"], "email": user["email"], "name": user.get("name"), "role": user.get("role")})
