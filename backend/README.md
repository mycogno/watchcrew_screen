# Backend (FastAPI)

This folder contains a simple FastAPI app that exposes `/generate_candidates`.

Run locally (from repository root):

```bash
# create venv (recommended)
python -m venv .venv
# activate (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt

# run from repo root
uvicorn backend.main:app --reload --port 8000

# or run from inside backend/
uvicorn main:app --reload --port 8000
```

CORS: allowed origins are taken from `BACKEND_ALLOWED_ORIGINS` env var (comma-separated). Default includes Vite dev origin `http://localhost:5173`.
