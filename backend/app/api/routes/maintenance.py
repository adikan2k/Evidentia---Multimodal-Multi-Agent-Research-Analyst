from fastapi import APIRouter, HTTPException
from typing import Dict, Any

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

# Store references to jobs and reports (will be set from main.py)
_jobs_ref = None
_reports_ref = None

def set_stores(jobs, reports):
    global _jobs_ref, _reports_ref
    _jobs_ref = jobs
    _reports_ref = reports

async def delete_run_records(run_id: str):
    if _jobs_ref and run_id in _jobs_ref:
        del _jobs_ref[run_id]
    if _reports_ref and run_id in _reports_ref:
        del _reports_ref[run_id]
    # In real system: delete DB rows
    return True

async def delete_collection_for_run(run_id: str):
    # In real system: delete Qdrant collection
    return True

async def delete_minio_prefix(prefix: str):
    # In real system: delete MinIO objects
    return True

@router.delete("/delete-run/{run_id}")
async def delete_run(run_id: str):
    try:
        await delete_run_records(run_id)
        await delete_collection_for_run(run_id)
        await delete_minio_prefix(f"runs/{run_id}/")
        return {"status":"ok","run_id":run_id,"deleted":True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/runs")
async def list_runs():
    jobs_list = list(_jobs_ref.values()) if _jobs_ref else []
    reports_list = list(_reports_ref.keys()) if _reports_ref else []
    return {"jobs": jobs_list, "reports": reports_list}
