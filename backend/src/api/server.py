import os
import uuid
import logging
import shutil
import tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from backend.src.services.rule_indexer import clear_rules, index_pdf_files

# In-memory job store: { job_id: { status, result, error } }
jobs: Dict[str, Any] = {}


# ========== STEP 1: LOAD ENVIRONMENT VARIABLES ==========
# CRITICAL: Must happen BEFORE importing modules that need env vars
from dotenv import load_dotenv
load_dotenv(override=True)  
# Reads .env file and sets environment variables
# override=True = .env values replace system environment variables
# Example .env contents:
#   AZURE_SEARCH_KEY=abc123
#   APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...


# ========== STEP 2: INITIALIZE TELEMETRY ==========
from backend.src.api.telemetry import setup_telemetry
setup_telemetry()  
# ☝️ "Activates the sensors" - starts tracking all API activity
# Must happen AFTER load_dotenv() but BEFORE creating FastAPI app


# ========== STEP 3: IMPORT WORKFLOW GRAPH ==========
from backend.src.graph.workflow import app as compliance_graph
# Imports your LangGraph workflow (Indexer → Auditor)
# Renamed to 'compliance_graph' to avoid confusion with FastAPI's 'app'


# ========== STEP 4: CONFIGURE LOGGING ==========
logging.basicConfig(level=logging.INFO)  
# Sets default log level (INFO = important events, not debug spam)

logger = logging.getLogger("api-server")  
# Creates named logger for this module


# ========== STEP 5: CREATE FASTAPI APPLICATION ==========
app = FastAPI(
    # Metadata for auto-generated API documentation (Swagger UI)
    title="Brand Guardian AI API",
    description="API for auditing video content against brand compliance rules.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend HTML
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..", "frontend"))

@app.get("/", response_class=FileResponse)
def serve_landing():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/app", response_class=FileResponse)
def serve_app():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.html"))

@app.get("/architecture", response_class=FileResponse)
def serve_architecture():
    return FileResponse(os.path.join(FRONTEND_DIR, "architecture.html"))
# FastAPI automatically creates:
# - Interactive docs at http://localhost:8000/docs
# - OpenAPI schema at http://localhost:8000/openapi.json


# ========== STEP 6: DEFINE DATA MODELS (PYDANTIC) ==========

# --- REQUEST MODEL ---
class AuditRequest(BaseModel):
    """
    Defines the expected structure of incoming API requests.
    
    Pydantic validates that:
    - The request contains a 'video_url' field
    - The value is a string (not int, list, etc.)
    
    Example valid request:
    {
        "video_url": "https://youtu.be/abc123"
    }
    
    Example invalid request (raises 422 error):
    {
        "video_url": 12345  ← Not a string!
    }
    """
    video_url: str  # Required string field


# --- NESTED MODEL ---
class ComplianceIssue(BaseModel):
    """
    Defines the structure of a single compliance violation.
    
    Used inside AuditResponse to represent each violation found.
    """
    category: str      # Example: "Misleading Claims"
    severity: str      # Example: "CRITICAL"
    description: str   # Example: "Absolute guarantee detected at 00:32"


# --- RESPONSE MODEL ---
class AuditResponse(BaseModel):
    """
    Defines the structure of API responses.
    
    FastAPI uses this to:
    1. Validate the response before sending (catches bugs)
    2. Auto-generate API documentation (shows users what to expect)
    3. Provide type hints for frontend developers
    
    Example response:
    {
        "session_id": "ce6c43bb-c71a-4f16-a377-8b493502fee2",
        "video_id": "vid_ce6c43bb",
        "status": "FAIL",
        "final_report": "Video contains 2 critical violations...",
        "compliance_results": [
            {
                "category": "Misleading Claims",
                "severity": "CRITICAL",
                "description": "Absolute guarantee at 00:32"
            }
        ]
    }
    """
    session_id: str                           # Unique audit session ID
    video_id: str                             # Shortened video identifier
    status: str                               # PASS or FAIL
    final_report: str                         # AI-generated summary
    compliance_results: List[ComplianceIssue] # List of violations (can be empty)


# ========== BACKGROUND WORKER ==========

def _run_audit_job(job_id: str, initial_inputs: dict, tmp_path: str = None):
    """Runs the compliance graph in a background thread and stores the result."""
    try:
        final_state = compliance_graph.invoke(initial_inputs)
        jobs[job_id] = {
            "status": "complete",
            "result": {
                "session_id": job_id,
                "video_id": final_state.get("video_id", ""),
                "status": final_state.get("final_status", "UNKNOWN"),
                "final_report": final_state.get("final_report", "No report generated."),
                "compliance_results": final_state.get("compliance_results", []),
            }
        }
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        jobs[job_id] = {"status": "failed", "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ========== STEP 7: SUBMIT AUDIT (ASYNC) ==========

@app.post("/audit")
async def audit_video(request: AuditRequest):
    """Starts an async audit job and returns a job_id immediately."""
    import asyncio
    job_id = str(uuid.uuid4())
    video_id_short = f"vid_{job_id[:8]}"
    logger.info(f"Received Audit Request: {request.video_url} (Job: {job_id})")

    initial_inputs = {
        "video_url": request.video_url,
        "video_id": video_id_short,
        "compliance_results": [],
        "errors": []
    }

    jobs[job_id] = {"status": "pending"}
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_audit_job, job_id, initial_inputs, None)
    return {"job_id": job_id}


# ========== OPTION 2: SUBMIT UPLOAD AUDIT (ASYNC) ==========

@app.post("/audit-upload")
async def audit_video_with_upload(
    video_url: str = Form(...),
    video_title: str = Form(""),
    video_description: str = Form(""),
    video_file: UploadFile = File(...),
):
    """Saves uploaded video, starts async audit job, returns job_id immediately."""
    import asyncio
    job_id = str(uuid.uuid4())
    video_id_short = f"vid_{job_id[:8]}"
    logger.info(f"[Option 2] Upload audit: {video_url} (Job: {job_id})")

    suffix = "." + (video_file.filename.rsplit(".", 1)[-1] if "." in video_file.filename else "mp4")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(video_file.file, tmp)
    tmp.close()

    initial_inputs = {
        "video_url": video_url,
        "video_id": video_id_short,
        "video_file_path": tmp.name,
        "video_title": video_title,
        "video_description": video_description,
        "compliance_results": [],
        "errors": [],
    }

    jobs[job_id] = {"status": "pending"}
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_audit_job, job_id, initial_inputs, tmp.name)
    return {"job_id": job_id}


# ========== JOB STATUS ENDPOINT ==========

@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """Poll this endpoint to check audit progress and retrieve results."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# ========== RULE MANAGEMENT ENDPOINTS ==========

@app.post("/upload-rules")
async def upload_rules(
    files: List[UploadFile] = File(...),
    clear_first: bool = Form(False),
):
    """Upload PDF compliance rule files and index them into Azure AI Search."""
    tmp_paths = []
    try:
        for f in files:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            shutil.copyfileobj(f.file, tmp)
            tmp.close()
            tmp_paths.append(tmp.name)

        cleared = 0
        if clear_first:
            result = clear_rules()
            cleared = result.get("deleted", 0)
            logger.info(f"Cleared {cleared} existing rule chunks.")

        result = index_pdf_files(tmp_paths)
        return {
            "status": "success",
            "cleared_chunks": cleared,
            "files_processed": result["files_processed"],
            "chunks_indexed": result["chunks_indexed"]
        }
    except Exception as e:
        logger.error(f"Rule upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in tmp_paths:
            if os.path.exists(path):
                os.remove(path)


@app.post("/clear-rules")
def clear_all_rules():
    """Delete all compliance rule documents from Azure AI Search index."""
    try:
        result = clear_rules()
        return {"status": "success", "deleted_chunks": result["deleted"]}
    except Exception as e:
        logger.error(f"Clear rules failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== STEP 8: HEALTH CHECK ENDPOINT ==========
@app.get("/health")
# ↑ GET request at http://localhost:8000/health
def health_check():
    """
    Simple endpoint to verify the API is running.
    
    Used by:
    - Load balancers (to check if server is alive)
    - Monitoring systems (uptime checks)
    - Developers (quick test that server started)
    
    Example usage:
    curl http://localhost:8000/health
    
    Response:
    {
        "status": "healthy",
        "service": "Brand Guardian AI"
    }
    """
    return {"status": "healthy", "service": "Brand Guardian AI"}
    # FastAPI automatically converts dict to JSON response


# ========== STEP 9: RUN INSTRUCTIONS (IN COMMENTS) ==========
'''
To execute: 
uv run uvicorn backend.src.api.server:app --reload

Command breakdown:
- uv run          = Run with UV package manager
- uvicorn         = ASGI server (like Gunicorn but async)
- backend.src.api.server:app = Python path to FastAPI app object
- --reload        = Auto-restart server when code changes (dev mode)

Server starts at: http://localhost:8000

Access points:
- API Docs:    http://localhost:8000/docs (interactive Swagger UI)
- Health:      http://localhost:8000/health
- Main API:    POST http://localhost:8000/audit
'''

'''
## How the API Works (Request Flow)
```
1. Client sends POST request:
   POST http://localhost:8000/audit
   Body: {"video_url": "https://youtu.be/abc123"}
   
2. FastAPI receives request:
   - Validates request matches AuditRequest model
   - Calls audit_video() function
   
3. audit_video() executes:
   - Generates session ID
   - Prepares initial_inputs dict
   - Calls compliance_graph.invoke()
   
4. LangGraph workflow runs:
   START → Indexer → Auditor → END
   
5. Function returns AuditResponse:
   - FastAPI validates response matches model
   - Converts Pydantic object to JSON
   - Sends HTTP response to client
   
6. Azure Monitor captures:
   - Request duration
   - HTTP status code
   - Any errors
   - Graph execution trace

'''