from fastapi import APIRouter, HTTPException
from ..database import users_collection
from ..schemas import UserCreate, LoginRequest, UserResponse, TokenResponse
from ..security import hash_password, verify_password, create_access_token

router = APIRouter()

@router.post("/register", response_model=UserResponse)
async def register(data: UserCreate):
    if await users_collection.find_one({"email": data.email.lower()}):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    result = await users_collection.insert_one({
        "nome": data.nome.strip(),
        "email": data.email.lower(),
        "senha": hash_password(data.senha),
    })

    return UserResponse(
        id=str(result.inserted_id),
        nome=data.nome.strip(),
        email=data.email.lower(),
    )

@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    user = await users_collection.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.senha, user["senha"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    return TokenResponse(access_token=create_access_token(str(user["_id"])))
