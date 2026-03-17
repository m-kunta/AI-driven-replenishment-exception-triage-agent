"""CSV ingestion adapter for reading exception data from CSV files."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from loguru import logger

from src.ingestion.base_adapter import BaseIngestionAdapter
from src.utils.exceptions import IngestionError


class CsvIngestionAdapter(BaseIngestionAdapter):
    """Reads exception records from a CSV file.

    Handles UTF-8 and UTF-8-BOM encodings. Returns raw dicts with all values
    as strings — the normalizer handles type coercion downstream.
    """

    def __init__(self, file_path: str, delimiter: str = ",") -> None:
        self.file_path = Path(file_path)
        self.delimiter = delimiter

    def validate_connection(self) -> bool:
        """Check that the CSV file exists and is readable."""
        if not self.file_path.exists():
            logger.error(f"CSV file not found: {self.file_path}")
            return False
        if not self.file_path.is_file():
            logger.error(f"Path is not a file: {self.file_path}")
            return False
        return True

    def fetch(self) -> List[Dict]:
        """Read all rows from the CSV file and return as list of dicts.

        Returns:
            List of raw dictionaries, one per CSV row.

        Raises:
            IngestionError: If the file cannot be read or parsed.
        """
        if not self.validate_connection():
            raise IngestionError(f"CSV file not accessible: {self.file_path}")

        records: List[Dict] = []
        skipped = 0

        # Try UTF-8-BOM first, fall back to UTF-8
        encoding = self._detect_encoding()

        try:
            with open(self.file_path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)

                if reader.fieldnames is None:
                    raise IngestionError(f"CSV file has no header row: {self.file_path}")

                for row_num, row in enumerate(reader, start=2):  # row 1 is header
                    # Skip completely empty rows
                    if all(v is None or v.strip() == "" for v in row.values()):
                        logger.debug(f"Skipping empty row {row_num}")
                        skipped += 1
                        continue
                    records.append(dict(row))

        except csv.Error as e:
            raise IngestionError(
                f"CSV parse error in {self.file_path} at row {row_num}: {e}"
            ) from e
        except UnicodeDecodeError as e:
            raise IngestionError(
                f"Encoding error reading {self.file_path}: {e}"
            ) from e

        logger.info(
            f"CSV ingestion complete: {len(records)} rows read, "
            f"{skipped} rows skipped from {self.file_path}"
        )
        return records

    def _detect_encoding(self) -> str:
        """Detect if file uses UTF-8-BOM encoding."""
        try:
            with open(self.file_path, "rb") as f:
                bom = f.read(3)
            if bom == b"\xef\xbb\xbf":
                return "utf-8-sig"
        except OSError:
            pass
        return "utf-8"
