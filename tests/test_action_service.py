import asyncio
import pytest
from datetime import date
from typing import Tuple, Dict, Any

from src.db.action_store import ActionStore
from src.actions.service import ActionService
from src.actions.adapters import BaseActionAdapter
from src.models import ActionRequest, ActionType

class MockAdapter(BaseActionAdapter):
    def __init__(self, succeed=True):
        self.succeed = succeed
        
    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        if self.succeed:
            return True, "", {"remote": "ok"}
        return False, "Failed downstream", {"err": "1"}

def test_action_service_success():
    store = ActionStore(db_path=":memory:")
    service = ActionService(store, adapter=MockAdapter(succeed=True))
    
    req = ActionRequest(
        request_id="req-1", exception_id="e-1", run_date=date.today(),
        action_type=ActionType.DEFER, requested_by="u1", requested_by_role="r1", payload={}
    )
    result = asyncio.run(service.submit_action(req))
    assert result["status"] == "completed"
    assert result["downstream_response"]["remote"] == "ok"

def test_action_service_failure_and_retry():
    store = ActionStore(db_path=":memory:")
    adapter = MockAdapter(succeed=False)
    service = ActionService(store, adapter=adapter)
    
    req = ActionRequest(
        request_id="req-2", exception_id="e-2", run_date=date.today(),
        action_type=ActionType.STORE_CHECK, requested_by="u1", requested_by_role="r1", payload={}
    )
    result = asyncio.run(service.submit_action(req))
    assert result["status"] == "failed"
    assert result["failure_reason"] == "Failed downstream"
    
    # Now retry with successful adapter
    adapter.succeed = True
    retry_res = asyncio.run(service.retry_action("req-2"))
    assert retry_res["status"] == "completed"
