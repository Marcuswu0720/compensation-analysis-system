import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

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

# Cache-busting for /static/js|css references in the two hand-written HTML
# shells below. Found against a real deploy: dashboard.js changed (a new
# 用工类型 filter/column), but a returning browser kept serving its cached
# copy of the OLD dashboard.js against the freshly-fetched NEW dashboard.html
# - the two disagreed on the table's column count, so the UI silently
# rendered shifted-by-one-column data. FastAPI's StaticFiles mount doesn't
# send any cache-preventing headers, so a browser is free to cache
# `/static/js/dashboard.js` under heuristic caching rules indefinitely.
# Rather than trying to defeat caching entirely (bad for load times), each
# `/static/...` reference gets a `?v=<version>` query string appended -
# computed once at process startup from every static file's mtime (deploying
# is always a fresh process start here, so this doesn't need to detect
# changes at runtime), so any file that changed across a deploy gets a new
# URL and is fetched fresh; unchanged files keep browsers' existing cache.
_STATIC_ASSET_VERSION = str(int(max((p.stat().st_mtime for p in (FRONTEND_DIR / "static").rglob("*") if p.is_file()), default=0)))
_STATIC_SRC_RE = re.compile(r'((?:src|href)="/static/[^"?]+)"')


def _render_html_with_cache_busting(path: Path) -> HTMLResponse:
    html = path.read_text(encoding="utf-8")
    html = _STATIC_SRC_RE.sub(rf'\1?v={_STATIC_ASSET_VERSION}"', html)
    return HTMLResponse(html)


@app.get("/")
def index():
    return _render_html_with_cache_busting(FRONTEND_DIR / "login.html")


@app.get("/dashboard")
def dashboard():
    return _render_html_with_cache_busting(FRONTEND_DIR / "dashboard.html")


@app.get("/health")
def health():
    return {"ok": True}
