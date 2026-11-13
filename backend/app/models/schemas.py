"""Schemas Pydantic de entrada da API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.url_guard import UnsafeUrlError, check_url_syntax
from app.core.validators import normalize_instagram_username

InventoryParserKey = Literal["auto", "azul", "hazul", "avance", "generic", "playwright"]
UF = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
    "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


def _check_url(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    value = str(value).strip()
    try:
        check_url_syntax(value)
    except UnsafeUrlError as exc:
        raise ValueError(str(exc)) from exc
    return value


class CompanyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    website: str | None = None
    inventory_url: str | None = None
    inventory_parser: InventoryParserKey = "auto"
    instagram: str | None = Field(default=None, description="Username, @username ou URL do perfil")
    segment: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    active: bool = True
    inventory_frequency_hours: int = Field(default=24, ge=0, le=720, description="0 = somente manual")
    instagram_frequency_hours: int = Field(default=24, ge=0, le=720, description="0 = somente manual")
    competitor_ids: list[str] = Field(default_factory=list, max_length=20)
    min_model_stock: int = Field(default=3, ge=1, le=50)
    load_more: bool = False

    @field_validator("website", "inventory_url")
    @classmethod
    def _urls(cls, value: str | None) -> str | None:
        return _check_url(value)

    @field_validator("instagram")
    @classmethod
    def _username(cls, value: str | None) -> str | None:
        return normalize_instagram_username(value)

    @field_validator("state")
    @classmethod
    def _uf(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().upper()
        if value not in UF:
            raise ValueError("UF inválida")
        return value

    @field_validator("competitor_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(v for v in value if v))


class CompetitorsIn(BaseModel):
    competitor_ids: list[str] = Field(default_factory=list, max_length=20)


class ManualSnapshotIn(BaseModel):
    collected_at: datetime
    followers: int | None = Field(default=None, ge=0)
    following: int | None = Field(default=None, ge=0)
    media_count: int | None = Field(default=None, ge=0)
    note: str = Field(min_length=3, max_length=500, description="Fonte da informação (obrigatório)")


class PostVehicleLinkIn(BaseModel):
    post_id: str
    vehicle_id: str
    note: str | None = Field(default=None, max_length=500)


class BriefingIn(BaseModel):
    period_days: int = Field(default=30, ge=7, le=365)
    title: str | None = Field(default=None, max_length=160)
