"""
server.py — FastAPI REST API for Video Gen v2

Endpoints:
  POST /generate          — start a video generation job
  GET  /status/{job_id}   — poll job status
  GET  /download/{job_id} — download completed MP4
  GET  /health            — healthcheck
  GET  /templates         — list available templates

Usage:
  uvicorn server:app --host 0.0.0.0 --port 8000

Example call:
  curl -X POST http://localhost:8000/generate \
    -H "Content-Type: application/json" \
    -d '{"topic":"在便利店偶遇朋友","template":"english_learning"}'

  curl http://localhost:8000/status/abc12345

  curl -o video.mp4 http://localhost:8000/download/abc12345
"""

import sys
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).parent
SRC  = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import OUTPUT_DIR, DEFAULT_TEMPLATE
from templates import list_templates

app = FastAPI(
    title="Video Gen v2 API",
    description="AI English Learning Short Video Generator",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def index():
    return FileResponse("index.html")

# ── Job registry ──────────────────────────────────────────────────────────────

_jobs: Dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)   # at most 2 concurrent renders


# ── Request / Response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    # AI pipeline
    topic:    str  = Field("", description="Dialogue topic (AI mode)")
    template: str  = Field(DEFAULT_TEMPLATE, description="Template name")
    voice:    str  = Field("en", description="TTS voice key")
    mode:     str  = Field("ai", description="ai | mixed | demo | mixed-demo")

    # Direct script (skip AI)
    data: dict = Field({}, description="Pre-written script dict (optional)")


class JobResponse(BaseModel):
    job_id:  str
    status:  str    # pending | running | done | error
    message: str = ""
    download_url: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_job_id() -> str:
    return uuid.uuid4().hex[:10]


def _run_job(job_id: str, req: GenerateRequest):
    """Blocking render — runs in thread pool."""
    _jobs[job_id]["status"] = "running"
    try:
        output_name = f"{job_id}.mp4"

        if req.mode in ("mixed", "mixed-demo", "mixed-multi"):
            from pipeline import MixedPipeline
            data = req.data or _MIXED_DEMO
            MixedPipeline(
                zh_voice="zh" if "zh" in req.voice else "zh",
                en_voice=req.voice if req.voice in ("en", "en-m", "teacher") else "en",
            ).run(data, output_name)

        elif req.mode == "demo":
            from pipeline import Pipeline
            Pipeline(req.template, req.voice).run_demo(output_name)

        elif req.data:
            from pipeline import Pipeline
            Pipeline(req.template, req.voice).run_script(req.data, output_name)

        else:
            from pipeline import Pipeline
            if not req.topic:
                raise ValueError("topic is required for mode=ai")
            Pipeline(req.template, req.voice).run_topic(req.topic, output_name)

        out_path = str(OUTPUT_DIR / output_name)
        _jobs[job_id]["status"]  = "done"
        _jobs[job_id]["output"]  = out_path
        size_mb = Path(out_path).stat().st_size / 1024 / 1024
        _jobs[job_id]["message"] = f"{size_mb:.1f} MB"

    except Exception as exc:
        _jobs[job_id]["status"]  = "error"
        _jobs[job_id]["message"] = str(exc)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "jobs": len(_jobs)}


@app.get("/templates")
def templates():
    return {"templates": list_templates()}


@app.post("/generate", response_model=JobResponse)
def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    """Start a video generation job. Returns job_id immediately."""
    job_id = _make_job_id()
    _jobs[job_id] = {"status": "pending", "output": "", "message": ""}

    # Submit to thread pool (non-blocking for the API)
    background_tasks.add_task(
        asyncio.get_event_loop().run_in_executor,
        _executor,
        _run_job,
        job_id,
        req,
    )

    return JobResponse(
        job_id=job_id,
        status="pending",
        message=f"Job queued. Poll /status/{job_id}",
    )


@app.get("/status/{job_id}", response_model=JobResponse)
def status(job_id: str):
    """Poll job status."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    return JobResponse(
        job_id=job_id,
        status=job["status"],
        message=job.get("message", ""),
        download_url=(f"/download/{job_id}"
                      if job["status"] == "done" else ""),
    )


@app.get("/download/{job_id}")
def download(job_id: str):
    """Download completed MP4."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(409, detail=f"Job status: {job['status']}")
    path = job["output"]
    if not Path(path).exists():
        raise HTTPException(404, detail="Output file missing")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"video_{job_id}.mp4",
    )


@app.get("/jobs")
def list_jobs():
    """List all jobs and their statuses."""
    return {
        jid: {"status": j["status"], "message": j.get("message", "")}
        for jid, j in _jobs.items()
    }


# ── Demo data ─────────────────────────────────────────────────────────────────

_MIXED_DEMO = {
    "paragraphs": [
        {
            "text":  "fix，如果这次launch再出error，你全年的bonus肯定泡汤！",
            "slide": "1/2",
            "words": [
                {"word": "fix",    "pos": "v.",    "meaning": "修复"},
                {"word": "launch", "pos": "n./v.", "meaning": "上线"},
                {"word": "error",  "pos": "n.",    "meaning": "错误"},
                {"word": "bonus",  "pos": "n.",    "meaning": "奖金"},
            ],
        },
        {
            "text":  "我要看到concrete plan，否则你自己跟board解释！",
            "slide": "2/2",
            "words": [
                {"word": "concrete plan", "pos": "phrase", "meaning": "具体方案"},
                {"word": "board",         "pos": "n.",     "meaning": "董事会"},
            ],
        },
    ]
}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)


# ── Frontend serving ──────────────────────────────────────────────────────────
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

@app.get("/", response_class=HTMLResponse)
def frontend():
    """Serve the web UI."""
    p = ROOT / "frontend.html"
    return p.read_text(encoding="utf-8") if p.exists() else "<h1>frontend.html not found</h1>"

# Serve generated videos for inline preview
@app.get("/output/{filename}")
def serve_output(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(path), media_type="video/mp4")
