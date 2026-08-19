# CodeLens

Minimal CodeLens foundation: FastAPI backend, a shared Python Tree-sitter parser interface for Python, JavaScript, TypeScript, and Java, and a React/Vite frontend.

## Run the backend

```bash
python3 -m pip install -r requirements.txt
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173` and proxies `/api` requests to FastAPI at `http://127.0.0.1:8000`.

## AI explanation configuration

Copy `.env.example` to `.env` at the project root and set the backend-only provider values:

```bash
cp .env.example .env
```

```dotenv
AI_API_KEY=your-api-key
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=openai/gpt-oss-20b
```

The backend loads `.env` automatically. `.env` is ignored by Git; commit `.env.example`, never real credentials.

## Parser tests

```bash
cd backend
python3 -m pytest
```
