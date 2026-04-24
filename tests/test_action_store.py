import pytest
from src.db.action_store import ActionStore

def test_action_store_crud():
    store = ActionStore(db_path=":memory:")
    
    # 1. Insert action
    record1 = store.insert_action(
        request_id="req-123",
        exception_id="EXC-999",
        run_date="2026-04-24",
        action_type="CREATE_REVIEW",
        requested_by="admin",
        requested_by_role="analyst",
        payload={"note": "test"}
    )
    assert record1["request_id"] == "req-123"
    assert record1["status"] == "queued"
    
    # 2. Test Idempotency
    record2 = store.insert_action(
        request_id="req-123",
        exception_id="EXC-999",
        run_date="2026-04-24",
        action_type="DIFFERENT",
        requested_by="other",
        requested_by_role="analyst",
        payload={}
    )
    assert record2["action_type"] == "CREATE_REVIEW" # original preserved
    
    # 3. Update status
    store.update_action_status("req-123", "completed", downstream_response={"ok": True})
    updated = store.get_action("req-123")
    assert updated["status"] == "completed"
    assert updated["downstream_response"]["ok"] is True
    
    # 4. Get by exception
    actions = store.get_actions_for_exception("EXC-999")
    assert len(actions) == 1
    assert actions[0]["request_id"] == "req-123"
