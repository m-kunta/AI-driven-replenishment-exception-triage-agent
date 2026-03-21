"""Schema validation utilities for canonical and enriched exception schemas.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError

from src.models import CanonicalException, EnrichedExceptionSchema
from src.utils.exceptions import IngestionError, EnrichmentError


SCHEMA_DIR = Path(__file__).parent.parent.parent / "data" / "schema"


def load_json_schema(schema_name: str) -> Dict[str, Any]:
    """Load a JSON schema file from the schema directory.

    Args:
        schema_name: Filename of the schema (e.g., 'canonical_exception_schema.json').

    Returns:
        Parsed JSON schema as a dictionary.
    """
    schema_path = SCHEMA_DIR / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with open(schema_path, "r") as f:
        return json.load(f)


def validate_canonical_exception(data: Dict[str, Any]) -> CanonicalException:
    """Validate a dictionary against the CanonicalException schema.

    Args:
        data: Raw dictionary to validate.

    Returns:
        Validated CanonicalException instance.

    Raises:
        IngestionError: If validation fails.
    """
    try:
        return CanonicalException.model_validate(data)
    except ValidationError as e:
        raise IngestionError(f"Canonical exception validation failed: {e}") from e


def validate_enriched_exception(data: Dict[str, Any]) -> EnrichedExceptionSchema:
    """Validate a dictionary against the EnrichedExceptionSchema.

    Args:
        data: Dictionary to validate.

    Returns:
        Validated EnrichedExceptionSchema instance.

    Raises:
        EnrichmentError: If validation fails.
    """
    try:
        return EnrichedExceptionSchema.model_validate(data)
    except ValidationError as e:
        raise EnrichmentError(f"Enriched exception validation failed: {e}") from e


def validate_canonical_batch(records: List[Dict[str, Any]]) -> tuple[List[CanonicalException], List[Dict[str, Any]]]:
    """Validate a batch of records against the CanonicalException schema.

    Args:
        records: List of raw dictionaries to validate.

    Returns:
        Tuple of (valid CanonicalException list, list of invalid records with error details).
    """
    valid = []
    invalid = []
    for i, record in enumerate(records):
        try:
            valid.append(CanonicalException.model_validate(record))
        except ValidationError as e:
            invalid.append({
                "row_index": i,
                "record": record,
                "errors": e.errors(),
            })
    return valid, invalid
