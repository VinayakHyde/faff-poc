# Backend

FastAPI backend for the Faff POC personal assistant agent.

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in OPENAI_API_KEY
```

## Run

```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `curl http://127.0.0.1:8000/healthz`

## Layout

```
app/
  main.py        FastAPI entry, route registration
  config.py      env-loaded settings (OPENAI_API_KEY, model, host, port)
  models.py      pydantic contracts (CandidateTask, PreferenceUpdate, TraceEvent, ...)
  agents/        sub-agents (one file per agent)
  tools/         shared tools (gmail_search, calendar_search, web_search)
data/users/      per-persona profile.md + fixtures
```
