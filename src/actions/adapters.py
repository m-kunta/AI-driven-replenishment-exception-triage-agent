from abc import ABC, abstractmethod
from typing import Dict, Tuple, Any

class BaseActionAdapter(ABC):
    @abstractmethod
    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes the action against a downstream system.
        
        Returns:
            Tuple containing:
            - success (bool): True if successful
            - failure_reason (str): Empty if successful, otherwise reason for failure
            - downstream_response (dict): Any response payload from the downstream system
        """
        pass

class GenericWebhookAdapter(BaseActionAdapter):
    """A generic webhook adapter for v1 to mock or send simple HTTP payloads."""
    
    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        # In a real scenario, this would use httpx to hit an external URL.
        # For Phase 13 v1, we mock a successful execution (or failure if requested).
        import asyncio
        await asyncio.sleep(0.5) # Simulate network latency
        
        # Simulating a failure for testing purposes
        if payload.get("simulate_failure"):
            return False, "Simulated downstream failure", {"error": "simulated_error", "status_code": 500}
            
        return True, "", {"status": "accepted", "remote_id": f"EXT-{action_type}-{id(payload)}"}
