from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .bootstrap import seed_admin_from_env
from .database import Base, engine
from .migrations import run_migrations
from .routers import auth, chat, export, query, upload

Base.metadata.create_all(bind=engine)
run_migrations(engine)
seed_admin_from_env()

app = FastAPI(title="尼日利亚薪酬人力成本分析工具")

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(query.router)
app.include_router(chat.router)
app.include_router(export.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/health")
def health():
    return {"ok": True}
