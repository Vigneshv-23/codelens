# CodeLens

**Codebase intelligence for understanding how a repository fits together.**

CodeLens turns a GitHub repository or local ZIP archive into an interactive symbol graph. Explore files, classes, methods, functions, imports, calls, inheritance, implementation, and containment relationships from one developer-focused workspace.

The optional AI explanation layer is grounded in the analyzer's results. It explains a selected symbol using bounded source code and graph context—without embeddings, vector databases, RAG pipelines, or full-repository prompts.

## What you can do

- Analyze repositories from GitHub URLs or local ZIP files
- Parse Python, JavaScript, TypeScript, and Java source code
- Explore symbols and file-level relationships visually
- Search symbols by name, type, language, or file path
- Switch between overview and focused neighborhood views
- Inspect callers, callees, dependencies, dependents, and parent symbols
- Open a syntax-highlighted source view for selected symbols
- Ask grounded AI questions about selected code:
  - Explain this
  - How does this work?
  - Impact analysis
- Keep AI responses short, readable, and bounded to repository evidence

## Architecture

```text
Repository input
      │
      ▼
FastAPI analyzer ──► Tree-sitter parsing ──► Symbol and relationship graph
      │                                      │
      │                                      ▼
      └──────────────────────────────────► React + React Flow workspace
                                             │
                                             ▼
                                      Optional grounded AI explanations
```

### Backend

The backend is a FastAPI service responsible for repository ingestion, parsing, graph construction, source retrieval, and AI explanation requests.

- `backend/analyzer/` — parsing, symbols, relationships, and graph services
- `backend/routes/` — analysis, source, health, and explanation endpoints
- `backend/explanation/` — bounded context building, prompts, provider integration, and orchestration
- `backend/storage/` — in-memory analysis sessions
- `backend/tests/` — parser, graph, API, and explanation coverage

### Frontend

The frontend is a Vite-powered React application.

- `frontend/src/App.jsx` — application state and workspace orchestration
- `frontend/src/components/GraphToolbar.jsx` — search, view, and filter controls
- `frontend/src/components/NodeInspector.jsx` — symbol metadata, relationships, source actions, and AI controls
- `frontend/src/components/CodeViewer.jsx` — syntax-highlighted source inspection
- `frontend/src/components/MarkdownAnswer.jsx` — safe Markdown rendering for AI answers

## Requirements

- Python 3.10+
- Node.js 18+
- npm

## Quick start

### 1. Install backend dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 2. Start the backend

```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

The API runs at `http://127.0.0.1:8000`.

### 3. Install and start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. The Vite development server proxies `/api` requests to the backend.

## AI explanations

AI explanations are optional. CodeLens uses an OpenAI-compatible HTTP API from the backend, so the API key is never sent to the browser.

Create a local environment file from the committed template:

```bash
cp .env.example .env
```

Then configure your provider:

```dotenv
AI_API_KEY=your-api-key
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=openai/gpt-oss-20b
```

The backend loads `.env` automatically. Shell environment variables take precedence over values in the file.

### Grounding and limits

The explanation layer only receives bounded context for the selected symbol:

- Symbol metadata and source
- Parent and related symbols
- Callers and callees
- Dependencies and dependents
- Relevant imports

Hard limits prevent oversized prompts. Truncation is reported explicitly, provider failures are surfaced to the UI, and rate limits return a retryable response. No credentials or full repository contents are returned to the frontend.

## API overview

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Check backend availability |
| `POST /api/analyze/github` | Analyze a GitHub repository |
| `POST /api/analyze/upload` | Analyze an uploaded ZIP archive |
| `GET /api/source/{analysis_id}/{symbol_id}` | Retrieve selected symbol source |
| `POST /api/explain` | Generate a grounded explanation for a symbol |

## Testing

Run the complete backend test suite:

```bash
cd backend
python3 -m pytest -q
```

Build the frontend for production:

```bash
cd frontend
npm run build
```

## Security and privacy

- API keys stay on the backend
- `.env` is ignored by Git
- `.env.example` contains placeholders only
- AI prompts are limited to selected-symbol context and configured bounds
- AI output is rendered with React components rather than raw HTML injection
- Repository analysis sessions are stored in memory by default

Never commit real credentials. If a key is exposed, revoke it and issue a replacement immediately.

## Project status

CodeLens is an actively developed prototype for repository exploration and grounded code explanations. The analyzer and relationship graph remain the source of truth; AI is used only as an explanation layer on top of analyzed code.
