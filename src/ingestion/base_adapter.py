"""Abstract base class for all ingestion adapters.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class BaseIngestionAdapter(ABC):
    """Abstract base class for all ingestion adapters.

    All adapters return a list of raw exception dicts.
    Downstream normalizer converts these to canonical schema.
    """

    @abstractmethod
    def fetch(self) -> List[Dict]:
        """Fetch raw exception records from the source system."""
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate that the source system is reachable before fetching."""
        pass
