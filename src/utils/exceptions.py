"""Custom exception hierarchy for the Replenishment Triage Agent."""


class TriageAgentError(Exception):
    """Base exception for all triage agent errors."""
    pass


class ConfigurationError(TriageAgentError):
    """Raised when configuration is invalid or missing required values."""
    pass


class IngestionError(TriageAgentError):
    """Raised when data ingestion fails (parse errors, connection failures, etc.)."""
    pass


class EnrichmentError(TriageAgentError):
    """Raised when data enrichment fails."""
    pass


class AgentError(TriageAgentError):
    """Raised when the AI agent layer fails (API errors, parse failures, etc.)."""
    pass


class OutputError(TriageAgentError):
    """Raised when output generation fails (routing, alerting, briefing, logging)."""
    pass
