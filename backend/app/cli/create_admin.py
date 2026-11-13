"""Cria (ou redefine a senha de) um administrador.

Uso interativo:
    docker compose run --rm api python -m app.cli.create_admin --email voce@empresa.com --name "Seu Nome"
A senha é pedida no terminal (não aparece na tela nem em logs). Para automação:
    ... --password-stdin  (lê a senha da entrada padrão)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from email_validator import EmailNotValidError, validate_email

from app.core.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH, hash_password
from app.core.timeutil import utcnow
from app.db.mongo import create_client, wait_for_mongo


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass(f"Senha (mín. {MIN_PASSWORD_LENGTH} caracteres): ")
    second = getpass.getpass("Confirme a senha: ")
    if first != second:
        raise SystemExit("As senhas não conferem.")
    return first


async def main(email: str, name: str, password: str, reset: bool) -> None:
    settings = get_settings()
    client = create_client(settings)
    try:
        await wait_for_mongo(client, attempts=10)
        db = client[settings.mongo_db]
        existing = await db.users.find_one({"email": email})
        if existing and not reset:
            raise SystemExit("Usuário já existe. Use --reset para redefinir a senha.")
        doc = {"email": email, "name": name, "role": "admin", "active": True, "password_hash": hash_password(password)}
        if existing:
            await db.users.update_one({"_id": existing["_id"]}, {"$set": {**doc, "updated_at": utcnow()}})
            print(f"Senha redefinida para {email}.")
        else:
            await db.users.insert_one({**doc, "created_at": utcnow()})
            print(f"Administrador {email} criado.")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cria o administrador da plataforma")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrador")
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    try:
        email = validate_email(args.email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise SystemExit(f"E-mail inválido: {exc}") from exc
    password = read_password(args.password_stdin)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    asyncio.run(main(email, args.name, password, args.reset))
