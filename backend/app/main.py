from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.config import (ALLOWED_ORIGINS, BACKEND_DIR, PROD, PUBLIC_DOCS, UPLOAD_DIR,
                        WATCH_ENABLED, WEB_DIR)
# `auth` as a bare name is the router imported below; these are the
# authorisation module's own.
from app.auth import can_open_farm, current_user
from app.db import get_db, init_db
from app.models import Diagnosis, Farm, Problem
from app.engine import vision
from app.kb import get_kb
from app import voice
from app import cache, mosdac, notify, watch
from app import krishi as krishi_kb
from app.routers import auth, darpan, expert, farmer, geo, krishi, live, officials, weather


logging.basicConfig(
    level=os.environ.get("ANNRAKSHAK_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("annrakshak")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A laptop is told; a server that says it is production is stopped. Every
    # item is something a farmer or an officer would pay for.
    problems = config.start_checks()
    if problems and PROD:
        raise RuntimeError("refusing to start in production:\n  - " + "\n  - ".join(problems))
    for p in problems:
        log.warning("not production-ready: %s", p)

    get_kb()  # refuse to start on a broken knowledge base
    krishi_kb.index()  # ... or a broken Krishi help base
    init_db()
    tasks = [asyncio.create_task(cache.listen(notify.broker.deliver_local))]
    if WATCH_ENABLED:
        tasks.append(asyncio.create_task(watch.run_forever()))
        tasks.append(asyncio.create_task(mosdac.run_forever()))  # returns at once without an account
    yield
    for task in tasks:
        task.cancel()
    # Background loops talk to the network; one stuck on a dead socket must not
    # hold the process open. Give them a moment, then stop waiting.
    await asyncio.wait(tasks, timeout=3)


app = FastAPI(title="AnnRakshak API", version="0.2.0", lifespan=lifespan,
              # The schema of an authenticated API is not public business.
              docs_url="/docs" if PUBLIC_DOCS else None,
              redoc_url="/redoc" if PUBLIC_DOCS else None,
              openapi_url="/openapi.json" if PUBLIC_DOCS else None)

# One host serving both the app and this API is the normal deployment (see the
# Dockerfile) and makes no cross-origin request at all. ANNRAKSHAK_ORIGINS is
# for the other case: the app on its own domain, which then needs the session
# cookie to travel, which needs named origins — "*" and credentials cannot mix.
if ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
elif not PROD:
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """The last word, so a bug is a logged 500 with a sentence a screen can
    show — not a traceback on its way to a farmer's phone."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong at our end. Please try again."})

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")   # what services.save_upload writes


@app.get("/media/{name}")
def media(name: str, request: Request, db: Session = Depends(get_db)):
    """A photograph a farmer took of their own field.

    These were served straight off disk by a static mount: unguessable names,
    but a URL that leaks — in a screenshot, a shared link, a server log — was
    then a photograph of someone's farm to anyone who had it, for good. It now
    goes only to someone who may open that farm: the farmer it belongs to, or
    an officer. A name that matches nothing and a photo that is not yours get
    the same 404, because the difference between them is itself an answer."""
    if not MEDIA_NAME.match(name):
        raise HTTPException(404, "not found")
    farm = db.scalars(
        select(Farm).join(Problem, Problem.farm_id == Farm.id)
        .join(Diagnosis, Diagnosis.problem_id == Problem.id)
        .where(Diagnosis.image_path == name).limit(1)
    ).first()
    path = UPLOAD_DIR / name
    if farm is None or not path.exists() or not can_open_farm(current_user(request, db), farm, db):
        raise HTTPException(404, "not found")
    # Private: a shared cache must not hand this to the next person through it.
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})
_SAMPLES = BACKEND_DIR.parent / "data" / "processed" / "icar_640"
if _SAMPLES.exists():  # held-out demo images; absent on machines without the dataset
    app.mount("/samples", StaticFiles(directory=_SAMPLES), name="samples")
_EXTRA = BACKEND_DIR.parent / "data" / "processed" / "extra_640"
if _EXTRA.exists():  # held-out photos from the extra sources (blast, rust, field FAW)
    app.mount("/samples-extra", StaticFiles(directory=_EXTRA), name="samples-extra")
_MORE = BACKEND_DIR.parent / "data" / "processed" / "more_640"
if _MORE.exists():  # held-out cotton, soybean and more maize/rice photos
    app.mount("/samples-more", StaticFiles(directory=_MORE), name="samples-more")

app.include_router(auth.router)
app.include_router(krishi.router)
app.include_router(darpan.router)
app.include_router(geo.router)
app.include_router(farmer.router)
app.include_router(expert.router)
app.include_router(officials.router)
app.include_router(live.router)
app.include_router(weather.router)
app.include_router(voice.router)


@app.get("/health")
def health():
    kb = get_kb()
    return {
        "status": "ok",
        "service": "annrakshak-api",
        "kb": {"targets": len(kb.targets), "cues": len(kb.cues), "rules": len(kb.rules)},
        "model": vision.model_status(),
        "voice": voice.status(),
        "satellite_rain": mosdac.status(),
    }


# --------------------------------------------------------------------------
# The browser app, when this process is the one serving it
# --------------------------------------------------------------------------

def mount_web(target, web_dir) -> None:
    """Serve a built single-page app from `web_dir` on `target`.

    A function rather than a block at import time so it can be mounted on a
    throwaway app in a test — the behaviour here (a deep link survives a cold
    load, a path cannot walk out of the root) is production behaviour and wants
    covering like any other."""
    target.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")
    root = web_dir.resolve()

    @target.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        """Everything the API did not answer is the app itself.

        Every route inside a built app (/app/scan, /officer/queue) exists only
        in the browser, so a cold load of one must be answered with index.html
        rather than a 404. Registered last, so every API route wins first."""
        wanted = (web_dir / path).resolve()
        if path and root in wanted.parents and wanted.is_file():
            return FileResponse(wanted)        # favicon, manifest, the service worker
        index = web_dir / "index.html"
        if not index.is_file():
            raise HTTPException(404, "not found")
        # The shell is never cached: a deploy must reach a phone that still has
        # the old one, and the hashed files under /assets carry the caching.
        return FileResponse(index, headers={"Cache-Control": "no-store"})


if WEB_DIR and WEB_DIR.is_dir():
    mount_web(app, WEB_DIR)
