from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Annotated, Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger
from pydantic import BaseModel, Field

from src.main import run_triage_pipeline

# Configure base FastAPI app
app = FastAPI(
    title="Replenishment Triage API",
    description="FastAPI Backend for the AI-driven Exception Copilot",
    version="1.0.0",
)

security = HTTPBasic()

# Setup paths (Assuming running from root dir)
OUTPUT_LOGS_DIR = Path("output/logs")


def get_current_username(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    """Verifies HTTP Basic Auth credentials from environment variables."""
    # Pull secrets from environment
    expected_username = os.environ.get("API_USERNAME", "admin")
    expected_password = os.environ.get("API_PASSWORD", "secret123")

    is_correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"), expected_username.encode("utf8")
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"), expected_password.encode("utf8")
    )

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class PipelineTriggerRequest(BaseModel):
    """Payload to trigger the pipeline."""
    run_date: Optional[str] = Field(default=None, description="ISO Date string (YYYY-MM-DD)")
    sample: bool = Field(default=True, description="Force sample CSV output")
    no_alerts: bool = Field(default=True, description="Prevent real alert dispatching")
    dry_run: bool = Field(default=False, description="Do not call the AI")


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Basic healthcheck endpoint. No auth required."""
    return {"status": "ok", "service": "triage_api"}


@app.get("/exceptions/queue/{priority}/{run_date}")
def get_queue(
    priority: str,
    run_date: str,
    username: Annotated[str, Depends(get_current_username)],
) -> JSONResponse:
    """Read structured outputs from the priority JSON files."""
    priority = priority.upper()
    if priority not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        raise HTTPException(status_code=400, detail="Invalid priority level")

    file_name = f"{priority}_{run_date}.json"
    file_path = OUTPUT_LOGS_DIR / file_name

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Queue file {file_name} not found. Trigger the pipeline first."
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted queue file format")
    except Exception as e:
        logger.error(f"Failed to read queue file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pipeline/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_pipeline(
    payload: PipelineTriggerRequest,
    background_tasks: BackgroundTasks,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Triggers the massive daily batch logic asynchronously."""
    
    def run_pipeline_task():
        logger.info(f"Background execution starting for API User: {username}")
        try:
            run_triage_pipeline(
                config_path="config/config.yaml",
                run_date=payload.run_date,
                dry_run=payload.dry_run,
                no_alerts=payload.no_alerts,
                sample=payload.sample,
                verbose=True,
            )
            logger.info("Background execution completed.")
        except Exception as e:
            logger.error(f"Pipeline crashed during API execution: {e}")

    background_tasks.add_task(run_pipeline_task)
    
    return {
        "status": "queued",
        "message": "Pipeline triggered asynchronously. You can monitor the system logs.",
        "params": payload.model_dump()
    }
