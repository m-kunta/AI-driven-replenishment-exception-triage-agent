import json
import logging
from pathlib import Path
from typing import Dict, List

from src.models import Priority, TriageResult, TriageRunResult
from src.utils.config_loader import AppConfig

logger = logging.getLogger(__name__)


class PriorityRouter:
    """Routes triage results into priority-based queues.
    
    Consumes a TriageRunResult and outputs four separate JSON files
    (CRITICAL, HIGH, MEDIUM, LOW) sorted descending by financial impact.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.log_dir = Path(config.output.log_dir)

    def route(self, run_result: TriageRunResult) -> Dict[Priority, Path]:
        """Route triage results into distinct priority queue files.

        Args:
            run_result: The complete result container from the Layer 3 Reasoning Engine.

        Returns:
            Dict mapping Priority enum to the actual Path of the generated log file.
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize buckets
        queues: Dict[Priority, List[TriageResult]] = {
            Priority.CRITICAL: [],
            Priority.HIGH: [],
            Priority.MEDIUM: [],
            Priority.LOW: [],
        }

        # Partition results
        for result in run_result.triage_results:
            queues[result.priority].append(result)

        output_paths: Dict[Priority, Path] = {}
        
        # Sort and write each queue
        for priority, items in queues.items():
            # Sort descending by est_lost_sales_value, treat None as 0.0
            items.sort(
                key=lambda x: x.est_lost_sales_value if x.est_lost_sales_value is not None else 0.0,
                reverse=True
            )
            
            file_name = f"{priority.value}_{run_result.run_date}.json"
            file_path = self.log_dir / file_name
            
            with open(file_path, "w", encoding="utf-8") as f:
                # Use pydantic's model_dump to serialize accurately
                json.dump([item.model_dump(mode="json") for item in items], f, indent=2)
                
            output_paths[priority] = file_path
            logger.info("Routed %d %s exceptions to %s", len(items), priority.value, file_path)

        return output_paths
