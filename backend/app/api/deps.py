"""Dependências compartilhadas das rotas."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.core.security import decode_access_token
from app.core.timeutil import ensure_utc, utcnow
from app.models.common import to_object_id

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticação necessária",
                            headers={"WWW-Authenticate": "Bearer"})
    subject = decode_access_token(credentials.credentials)
    if not subject:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada",
                            headers={"WWW-Authenticate": "Bearer"})
    user = await db.users.find_one({"email": subject, "active": True}, {"password_hash": 0})
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo ou inexistente")
    return user


async def get_company(company_id: str, db: AsyncDatabase = Depends(get_db),
                      _user: dict = Depends(current_user)) -> dict:
    company = await db.companies.find_one({"_id": to_object_id(company_id, "empresa")})
    if company is None:
        raise HTTPException(404, "Empresa não encontrada")
    return company


class Period:
    """Período de análise: `days` OU `start`/`end` (ISO-8601). Padrão: últimos 30 dias."""

    def __init__(
        self,
        days: int | None = Query(None, ge=1, le=730, description="Últimos N dias"),
        start: datetime | None = Query(None),
        end: datetime | None = Query(None),
    ):
        end_dt = ensure_utc(end) or utcnow()
        if start is not None:
            start_dt = ensure_utc(start)
        else:
            start_dt = end_dt - timedelta(days=days or 30)
        if start_dt >= end_dt:
            raise HTTPException(422, "Período inválido: início deve ser anterior ao fim")
        self.start = start_dt
        self.end = end_dt
        self.days = round((end_dt - start_dt).total_seconds() / 86400)
