# VEIF & VEALS — MVP

MVP inicial com Vue 3 + Vite, FastAPI, MongoDB e JWT.

## Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Configure `.env` a partir de `.env.example`.

Swagger: http://localhost:8000/docs

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

## MongoDB

O backend espera MongoDB local por padrão:
mongodb://localhost:27017

Banco: veif_veals
Coleção: users

A senha é armazenada somente como hash bcrypt.
