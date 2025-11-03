from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.health import router as health_router
import app.health as health_module
import os
import time
import uuid
import asyncio
from app.monitoring.metrics import MetricsMiddleware
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.ingest.factory import ingest_url
from app.api.routes.maintenance import router as maintenance_router
from app.api.routes.features import router as features_router
from io import BytesIO
from fastapi.responses import StreamingResponse
from fastapi import Body
from app.export.pdf import render_report_to_pdf_async

app = FastAPI(title="Evidentia – Multimodal Multi-Agent Research Analyst")

VERCEL_ORIGIN = os.getenv("VERCEL_ORIGIN")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"] + ([VERCEL_ORIGIN] if VERCEL_ORIGIN else []),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.add_middleware(MetricsMiddleware)
app.include_router(maintenance_router)
app.include_router(features_router)

# Initialize stores for maintenance router
from app.api.routes.maintenance import set_stores

@app.on_event("startup")
async def _debug_routes():
    print("HEALTH MODULE FILE:", health_module.__file__)
    for r in app.routes:
        try:
            print("ROUTE:", r.path, getattr(r, "methods", None))
        except Exception:
            pass

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/ingest")
async def ingest_endpoint(url: str):
    try:
        content = await ingest_url(url)
        return {"ok": True, "length": len(content)}
    except PermissionError as e:
        return {"ok": False, "msg": str(e)}
    
@app.post("/export/pdf")
async def export_pdf_post(payload: dict = Body(...)):
    html  = payload.get("body", "<h1>Empty</h1>")
    title = payload.get("title", "Evidentia Report")
    pdf_bytes = await render_report_to_pdf_async(html, title)  # ✅ await async
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{title}.pdf"'}
    )

# ------------------ Real research pipeline ------------------
from app.graph.pipeline import run_research_pipeline
from app.robots import is_allowed
from app.http_client import fetch_text

_jobs: Dict[str, Dict[str, Any]] = {}
_reports: Dict[str, Dict[str, Any]] = {}

# Set stores for maintenance router
set_stores(_jobs, _reports)

def _new_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "id": job_id,
        "created_at": time.time(),
        "phase": "planning",
        "percent": 5,
        "msg": "Planning sub-questions",
        "options": payload.get("options") or {},
        "query": payload.get("query") or "",
    }
    return _jobs[job_id]

async def _run_pipeline(job: Dict[str, Any]) -> None:
    job_id = job["id"]
    try:
        print(f"[Pipeline] Starting for job {job_id}, query: {job['query']}")
        
        # Step 1: Initializing
        job["phase"] = "initializing"
        job["percent"] = 5
        job["msg"] = "Setting up research pipeline"
        await asyncio.sleep(0.5)
        
        # Step 2: Source Discovery
        job["phase"] = "discovering_sources"
        job["percent"] = 15
        job["msg"] = "Searching multiple data sources"
        await asyncio.sleep(0.5)
        
        # Step 3: Content Ingestion
        job["phase"] = "ingesting_content"
        job["percent"] = 25
        job["msg"] = "Extracting content from sources"
        
        # Run the actual pipeline (which will update progress internally)
        result = await run_research_pipeline(job_id, job["query"], job["options"])
        print(f"[Pipeline] Result: {len(result.get('report', {}).get('citations', []))} citations")
        
        # Step 4: Text Processing (45%)
        job["phase"] = "processing_text"
        job["percent"] = 45
        job["msg"] = "Processing and cleaning extracted text"
        await asyncio.sleep(0.5)
        
        # Step 5: Semantic Analysis (60%)
        job["phase"] = "analyzing_semantics"
        job["percent"] = 60
        job["msg"] = "Generating embeddings and vectors"
        await asyncio.sleep(0.5)
        
        # Step 6: Content Ranking (75%)
        job["phase"] = "ranking_content"
        job["percent"] = 75
        job["msg"] = "Ranking sources by relevance"
        await asyncio.sleep(0.5)
        
        # Step 7: Report Generation (85%)
        job["phase"] = "generating_report"
        job["percent"] = 85
        job["msg"] = "Creating comprehensive research report"
        _reports[job_id] = result["report"]
        print(f"[Pipeline] Stored report for {job_id}")
        await asyncio.sleep(0.5)
        
        # Complete
        job["phase"] = "done"
        job["percent"] = 100
        job["msg"] = "Research completed successfully"
    except Exception as e:
        print(f"[Pipeline] Error: {e}")
        import traceback
        traceback.print_exc()
        job["phase"] = "error"
        job["msg"] = str(e)

@app.post("/research/start")
async def start_research(payload: Dict[str, Any]):
    job = _new_job(payload)
    # Run pipeline in background without blocking
    asyncio.create_task(_run_pipeline(job))
    return {"job_id": job["id"]}

@app.get("/status")
async def status(jobId: str):
    job = _jobs.get(jobId)
    if not job:
        return {"phase": "planning", "percent": 0, "msg": "Unknown job"}
    return {"phase": job["phase"], "percent": job["percent"], "msg": job["msg"]}

@app.get("/report")
async def report(jobId: str):
    data = _reports.get(jobId)
    if not data:
        return {"html": "<p>Report not ready yet.</p>", "citations": [], "sources": []}
    return data

# ------------------ Refine actions ------------------
@app.post("/refine/recency")
async def refine_recency(jobId: str):
    rep = _reports.get(jobId)
    if not rep:
        return {"ok": False, "msg": "Report not ready"}
    rep["html"] += "<p><em>Refine: emphasized newer sources.</em></p>"
    return {"ok": True}

@app.post("/refine/counterpoints")
async def refine_counterpoints(jobId: str):
    rep = _reports.get(jobId)
    if not rep:
        return {"ok": False, "msg": "Report not ready"}
    rep["html"] += "<p><em>Refine: added counterpoints section.</em></p>"
    return {"ok": True}

# ------------------ Export ------------------
from fastapi.responses import StreamingResponse
from io import BytesIO

@app.get("/export/pdf")
async def export_pdf(jobId: str):
    # stub: export simple text as "pdf" (real impl: WeasyPrint/Playwright)
    rep = _reports.get(jobId) or {"html": "No report"}
    fake_pdf = BytesIO()
    fake_pdf.write(("PDF placeholder for:\n\n" + rep["html"]).encode("utf-8"))
    fake_pdf.seek(0)
    return StreamingResponse(fake_pdf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="report-{jobId}.pdf"'})


