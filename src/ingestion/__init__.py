"""Ingestion layer — adapters and normalization for exception data."""

from src.ingestion.base_adapter import BaseIngestionAdapter
from src.ingestion.csv_adapter import CsvIngestionAdapter
from src.ingestion.normalizer import Normalizer

__all__ = ["BaseIngestionAdapter", "CsvIngestionAdapter", "Normalizer"]
