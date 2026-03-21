"""Configuration loader with YAML parsing and environment variable resolution.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from src.utils.exceptions import ConfigurationError


# --- Config Models ---

class CsvConfig(BaseModel):
    path: str = "data/sample/exceptions_sample.csv"
    delimiter: str = ","
    date_format: str = "%Y-%m-%d"


class ApiConfig(BaseModel):
    endpoint: str = ""
    api_key: str = ""
    method: str = "GET"
    response_path: str = "data.exceptions"


class SqlConfig(BaseModel):
    connection_string: str = ""
    query_file: str = "config/exception_query.sql"


class IngestionConfig(BaseModel):
    adapter: str = "csv"
    csv: CsvConfig = Field(default_factory=CsvConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    sql: SqlConfig = Field(default_factory=SqlConfig)
    field_mapping: Dict[str, str] = Field(default_factory=dict)


class EnrichmentConfig(BaseModel):
    store_master_path: str = "data/sample/store_master_sample.csv"
    item_master_path: str = "data/sample/item_master_sample.csv"
    promo_calendar_path: str = "data/sample/promo_calendar_sample.csv"
    vendor_performance_path: str = "data/sample/vendor_performance_sample.csv"
    dc_inventory_path: str = "data/sample/dc_inventory_sample.csv"
    regional_signals_path: str = "data/regional_signals.json"
    parallel_workers: int = 4
    null_threshold_low_confidence: int = 3
    null_threshold_medium_confidence: int = 1
    promo_lift_factor: float = 1.4


class AgentConfig(BaseModel):
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4000
    batch_size: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: int = 5
    reasoning_trace_enabled: bool = False
    phantom_webhook_enabled: bool = True
    phantom_webhook_url: str = ""
    pattern_threshold: int = 3


class StoreTiersConfig(BaseModel):
    tier_1_min_weekly_sales_k: float = 1500
    tier_2_min_weekly_sales_k: float = 800
    tier_3_min_weekly_sales_k: float = 300
    tier_4_min_weekly_sales_k: float = 0


class PriorityRulesConfig(BaseModel):
    critical_max_days_supply_tier_1_on_promo: float = 1.5
    critical_max_days_supply_perishable: float = 1.0
    critical_min_vendor_pattern_count: int = 5
    high_max_days_supply_tier_1_2: float = 3.0


class AlertChannelConfig(BaseModel):
    type: str
    enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    from_address: Optional[str] = None
    to_addresses: Optional[List[str]] = None
    webhook_url: Optional[str] = None


class AlertingConfig(BaseModel):
    channels: List[AlertChannelConfig] = Field(default_factory=list)
    critical_sla_minutes: int = 60
    secondary_escalation_contact: str = ""


class OutputConfig(BaseModel):
    briefing_dir: str = "output/briefings"
    log_dir: str = "output/logs"
    format: str = "markdown"
    include_low_priority: bool = True
    max_exceptions_in_briefing: int = 10


class BacktestConfig(BaseModel):
    log_dir: str = "output/backtest"
    outcome_check_weeks: List[int] = Field(default_factory=lambda: [4, 8])


class AppConfig(BaseModel):
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    store_tiers: StoreTiersConfig = Field(default_factory=StoreTiersConfig)
    priority_rules: PriorityRulesConfig = Field(default_factory=PriorityRulesConfig)
    alerting: AlertingConfig = Field(default_factory=AlertingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)


# --- Environment Variable Resolution ---

ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${VAR_NAME} references in config values.

    Missing optional vars (alerting, webhooks) resolve to empty string.
    Missing required vars (ANTHROPIC_API_KEY) are caught at validation time.
    """
    if isinstance(value, str):
        def replace_match(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        return ENV_VAR_PATTERN.sub(replace_match, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


# --- Config Loader ---

def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to the config YAML file.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigurationError: If the config file is missing or invalid.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with open(path, "r") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse YAML config: {e}") from e

    if raw_config is None:
        raise ConfigurationError(f"Configuration file is empty: {config_path}")

    resolved_config = _resolve_env_vars(raw_config)

    try:
        config = AppConfig.model_validate(resolved_config)
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}") from e

    return config


def validate_required_env_vars(config: AppConfig, adapter: str = "csv", alerts_enabled: bool = False) -> None:
    """Validate that required environment variables are set based on runtime mode.

    Args:
        config: The loaded AppConfig.
        adapter: The active ingestion adapter type.
        alerts_enabled: Whether alerting is enabled.

    Raises:
        ConfigurationError: If a required env var is missing.
    """
    if not config.agent.anthropic_api_key:
        raise ConfigurationError("Missing required environment variable: ANTHROPIC_API_KEY")

    if adapter == "api":
        if not config.ingestion.api.endpoint:
            raise ConfigurationError("Missing required environment variable: EXCEPTION_API_ENDPOINT")
        if not config.ingestion.api.api_key:
            raise ConfigurationError("Missing required environment variable: EXCEPTION_API_KEY")

    if adapter == "sql":
        if not config.ingestion.sql.connection_string:
            raise ConfigurationError("Missing required environment variable: DB_CONNECTION_STRING")
