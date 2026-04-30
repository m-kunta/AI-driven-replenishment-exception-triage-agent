from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Annotated, Any, Dict, Optional, List

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger
from pydantic import BaseModel, Field

from src.main import run_triage_pipeline
from src.db.store import OverrideStore
from src.db.action_store import ActionStore
from src.actions.service import ActionService
from src.models import ActionRequest

# Configure base FastAPI app
app = FastAPI(
    title="Replenishment Triage API",
    description="FastAPI Backend for the AI-driven Exception Copilot",
    version="1.0.0",
)

security = HTTPBasic()

# Setup paths (Assuming running from root dir)
OUTPUT_LOGS_DIR = Path("output/logs")
OUTPUT_BRIEFINGS_DIR = Path("output/briefings")

override_store = OverrideStore()
action_store = ActionStore()
action_service = ActionService(action_store)


def parse_user_roles() -> Dict[str, str]:
    """Parse username-to-role mappings from server-side configuration."""
    raw = os.environ.get("API_USER_ROLES", "").strip()
    mappings: Dict[str, str] = {}
    if not raw:
        return mappings

    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        if ":" not in item:
            raise RuntimeError("API_USER_ROLES entries must use username:role format")
        username, role = (part.strip() for part in item.split(":", 1))
        role = role.lower()
        if not username:
            raise RuntimeError("API_USER_ROLES entries must include a username")
        if role not in {"analyst", "planner"}:
            raise RuntimeError("API_USER_ROLES roles must be either 'analyst' or 'planner'")
        mappings[username] = role
    return mappings


def get_current_username(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    """Verifies HTTP Basic Auth credentials from environment variables."""
    # Pull secrets from environment — both vars are required at runtime
    expected_username = os.environ.get("API_USERNAME", "admin")
    expected_password = os.environ.get("API_PASSWORD")
    if expected_password is None:
        raise RuntimeError("API_PASSWORD environment variable is not set")
    allowed_usernames = {expected_username, *parse_user_roles().keys()}

    is_correct_username = any(
        secrets.compare_digest(credentials.username.encode("utf8"), allowed.encode("utf8"))
        for allowed in allowed_usernames
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


def get_current_user_role(username: str) -> str:
    """Resolve the authenticated user's role from server-side configuration."""
    role = parse_user_roles().get(username)
    if role:
        return role

    role = os.environ.get("API_USER_ROLE", "analyst").strip().lower()
    if role not in {"analyst", "planner"}:
        raise RuntimeError("API_USER_ROLE must be either 'analyst' or 'planner'")
    return role


class PipelineTriggerRequest(BaseModel):
    """Payload to trigger the pipeline."""
    run_date: Optional[str] = Field(default=None, description="ISO Date string (YYYY-MM-DD)")
    sample: bool = Field(default=True, description="Force sample CSV output")
    no_alerts: bool = Field(default=True, description="Prevent real alert dispatching")
    dry_run: bool = Field(default=False, description="Do not call the AI")


class OverrideSubmitRequest(BaseModel):
    exception_id: str
    run_date: str
    enriched_input_snapshot: dict
    override_priority: Optional[str] = None
    override_root_cause: Optional[str] = None
    override_recommended_action: Optional[str] = None
    override_financial_impact_statement: Optional[str] = None
    override_planner_brief: Optional[str] = None
    override_compounding_risks: Optional[List[str]] = None
    analyst_note: Optional[str] = None


class OverrideRejectRequest(BaseModel):
    reason: Optional[str] = None


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Basic healthcheck endpoint. No auth required."""
    return {"status": "ok", "service": "triage_api"}


@app.get("/me")
def get_current_user_profile(
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, str]:
    """Return the authenticated username and resolved role."""
    return {"username": username, "role": get_current_user_role(username)}


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
    file_path = (OUTPUT_LOGS_DIR / file_name).resolve()
    if not str(file_path).startswith(str(OUTPUT_LOGS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid run_date")

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
        logger.error("Failed to read queue file: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pipeline/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_pipeline(
    payload: PipelineTriggerRequest,
    background_tasks: BackgroundTasks,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Triggers the massive daily batch logic asynchronously."""
    
    def run_pipeline_task():
        logger.info("Background execution starting for API User: {}", username)
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
            logger.error("Pipeline crashed during API execution: {}", e)

    background_tasks.add_task(run_pipeline_task)

    return {
        "status": "queued",
        "message": "Pipeline triggered asynchronously. You can monitor the system logs.",
        "params": payload.model_dump()
    }


@app.get("/runs")
def list_runs(
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """List available run dates derived from existing queue files in output/logs."""
    if not OUTPUT_LOGS_DIR.exists():
        return {"run_dates": []}

    _VALID_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    dates: set[str] = set()
    for f in OUTPUT_LOGS_DIR.glob("*_????-??-??.json"):
        # File name format: PRIORITY_YYYY-MM-DD.json — take the date portion.
        # Guard: only accept files whose prefix is a known priority so that
        # quarantine_*, exception_log_* and other files are not included.
        parts = f.stem.split("_", 1)
        if len(parts) == 2 and parts[0] in _VALID_PRIORITIES:
            dates.add(parts[1])

    return {"run_dates": sorted(dates, reverse=True)}


@app.get("/briefing/{run_date}")
def get_briefing(
    run_date: str,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Return the morning briefing markdown for a given run date."""
    file_path = (OUTPUT_BRIEFINGS_DIR / f"briefing_{run_date}.md").resolve()
    if not str(file_path).startswith(str(OUTPUT_BRIEFINGS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid run_date")

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Briefing for {run_date} not found. Trigger the pipeline first.",
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"run_date": run_date, "content": content}
    except Exception as e:
        logger.error("Failed to read briefing file: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/overrides", status_code=status.HTTP_201_CREATED)
def submit_override(
    payload: OverrideSubmitRequest,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Submit a new analyst override."""
    try:
        row_id = override_store.insert_override(
            exception_id=payload.exception_id,
            run_date=payload.run_date,
            analyst_username=username,
            enriched_input_snapshot=payload.enriched_input_snapshot,
            override_priority=payload.override_priority,
            override_root_cause=payload.override_root_cause,
            override_recommended_action=payload.override_recommended_action,
            override_financial_impact_statement=payload.override_financial_impact_statement,
            override_planner_brief=payload.override_planner_brief,
            override_compounding_risks=payload.override_compounding_risks,
            analyst_note=payload.analyst_note,
        )
        return {"id": row_id, "status": "pending", "message": "Override submitted for review"}
    except ValueError as e:
        logger.error("Validation error in submit_override: {}", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to submit override: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/overrides/pending")
def list_pending_overrides(
    username: Annotated[str, Depends(get_current_username)],
) -> List[Dict[str, Any]]:
    """List overrides awaiting lead planner approval."""
    try:
        return override_store.get_pending_overrides()
    except Exception as e:
        logger.error("Failed to list pending overrides: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/overrides/{override_id}/approve")
def approve_override(
    override_id: int,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Approve a pending override."""
    try:
        override_store.approve_override(override_id, approved_by=username)
        return {"status": "approved", "override_id": override_id}
    except Exception as e:
        logger.error("Failed to approve override: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/overrides/{override_id}/reject")
def reject_override(
    override_id: int,
    payload: OverrideRejectRequest,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Reject a pending override."""
    try:
        override_store.reject_override(override_id, rejected_by=username, reason=payload.reason)
        return {"status": "rejected", "override_id": override_id}
    except Exception as e:
        logger.error("Failed to reject override: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/actions", status_code=status.HTTP_201_CREATED)
async def submit_action(
    payload: ActionRequest,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Submit a downstream action for an exception."""
    try:
        # Enforce authenticated actor metadata at the API boundary.
        payload.requested_by = username
        payload.requested_by_role = get_current_user_role(username)
        return await action_service.submit_action(payload)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Failed to submit action: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/actions/{exception_id}")
def get_actions(
    exception_id: str,
    username: Annotated[str, Depends(get_current_username)],
) -> List[Dict[str, Any]]:
    """Get all actions for a specific exception."""
    try:
        return action_service.get_actions_for_exception(exception_id)
    except Exception as e:
        logger.error("Failed to get actions: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/actions/{request_id}/retry", status_code=status.HTTP_200_OK)
async def retry_action(
    request_id: str,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Retry a failed downstream action."""
    try:
        result = await action_service.retry_action(request_id)
        if not result:
            raise HTTPException(status_code=404, detail="Action not found")
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retry action: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
