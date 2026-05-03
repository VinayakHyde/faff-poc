from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import evals, personas
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Faff POC", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# API routes — register before the static mount so they aren't shadowed.
app.include_router(personas.router)
app.include_router(evals.router)


# Serve the vanilla-JS frontend at /. Catch-all html=True returns index.html
# for unknown paths so a future client-side router can handle them.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
