import logging
from typing import Optional, List
from src.db.action_store import ActionStore
from src.models import ActionRequest, ActionStatus, ActionType
from src.actions.adapters import BaseActionAdapter, GenericWebhookAdapter

logger = logging.getLogger(__name__)

class ActionService:
    def __init__(self, store: ActionStore, adapter: Optional[BaseActionAdapter] = None):
        self.store = store
        self.adapter = adapter or GenericWebhookAdapter()

    async def submit_action(self, request: ActionRequest) -> dict:
        """
        Validates request, inserts into DB (or retrieves if idempotent retry),
        and attempts to execute via adapter.
        """
        # 1. Store action (handles idempotency returning existing)
        record_dict = self.store.insert_action(
            request_id=request.request_id,
            exception_id=request.exception_id,
            run_date=request.run_date.isoformat(),
            action_type=request.action_type.value,
            requested_by=request.requested_by,
            requested_by_role=request.requested_by_role,
            payload=request.payload
        )
        
        # 2. Check if we actually need to execute it
        status = record_dict["status"]
        if status in (ActionStatus.COMPLETED.value, ActionStatus.SENT.value):
            logger.info(f"Action {request.request_id} already in status {status}, skipping execution.")
            return record_dict

        # 3. Mark as sent
        self.store.update_action_status(request.request_id, ActionStatus.SENT.value)

        # 4. Execute via adapter
        try:
            success, fail_reason, downstream_resp = await self.adapter.execute(
                action_type=request.action_type.value,
                payload=request.payload
            )
            
            new_status = ActionStatus.COMPLETED.value if success else ActionStatus.FAILED.value
            self.store.update_action_status(
                request.request_id, 
                new_status, 
                failure_reason=fail_reason if not success else None,
                downstream_response=downstream_resp
            )
            
        except Exception as e:
            logger.exception(f"Adapter execution failed for {request.request_id}")
            self.store.update_action_status(
                request.request_id, 
                ActionStatus.FAILED.value, 
                failure_reason=str(e)
            )

        # Return updated record
        updated_record = self.store.get_action(request.request_id)
        if not updated_record:
            raise RuntimeError(f"Action {request.request_id} disappeared after update")
        return updated_record
        
    def get_actions_for_exception(self, exception_id: str) -> List[dict]:
        return self.store.get_actions_for_exception(exception_id)
        
    async def retry_action(self, request_id: str) -> Optional[dict]:
        """Retry a failed action by repackaging it and submitting it again."""
        record_dict = self.store.get_action(request_id)
        if not record_dict:
            return None
            
        if record_dict["status"] == ActionStatus.COMPLETED.value:
            return record_dict
            
        # Repackage as ActionRequest
        from datetime import datetime
        req = ActionRequest(
            request_id=record_dict["request_id"],
            exception_id=record_dict["exception_id"],
            run_date=datetime.strptime(record_dict["run_date"], "%Y-%m-%d").date(),
            action_type=ActionType(record_dict["action_type"]),
            requested_by=record_dict["requested_by"],
            requested_by_role=record_dict["requested_by_role"],
            payload=record_dict["payload"]
        )
        return await self.submit_action(req)
