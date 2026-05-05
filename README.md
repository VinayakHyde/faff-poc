# Faff POC

Daily-running personal-assistant POC: an orchestrator fans out to nine
sub-agents (calendar, email, food, travel, finance, dates, shopping, todos,
events) over a persona's Gmail + Calendar + profile snapshot, scores the
resulting candidate tasks against a rubric, reframes the survivors as
user-facing messages, and streams the whole thing live over SSE to a
vanilla-JS frontend.

## Prerequisites

- Python 3.11+
- An `OPENAI_API_KEY` (and optionally `TAVILY_API_KEY` for web search)

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY (and TAVILY_API_KEY if you want shopping/web-search)
```

## Run

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` — pick a persona on the left, hit **Simulate
daily cron job**, watch the trace stream in.

Health check: `curl http://127.0.0.1:8000/healthz`

## Personas

Four bundled personas under `backend/data/users/`: `aditi`, `arjun`,
`devendra`, `meera`. Each has a `profile.md` and a `fixtures/<date>.json`
daily payload. Switching personas in the UI keeps each one's chat / live
run independent — switching mid-run doesn't cancel anything.

## Evals

Per-agent LLM-as-judge eval harness:

```bash
cd backend
source venv/bin/activate
python -m eval.run <agent>          # e.g. todos, calendar, email_triage
python -m eval.history <agent>      # past run history for that agent
```

Results land in `backend/eval/results/`. The **Evals** button in the top
right of the UI surfaces the trajectory chart + per-agent detail.

## Layout

```
backend/
  app/         FastAPI app, agents, tools, orchestrator, rubric, messenger
  data/users/  per-persona profile.md + fixtures
  eval/        eval harness, judge prompts, golden sets, results
frontend/
  index.html   single-page UI
  main.js      vanilla JS — sidebar, profile/email/calendar/golden tabs,
               per-persona run-panel chat with SSE streaming
  styles.css
```
