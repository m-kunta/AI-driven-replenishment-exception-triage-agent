import os
import sys
import click
import pandas as pd
from datetime import datetime
from loguru import logger
from typing import Dict, Any

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config_loader import load_config

def calculate_metrics(merged_df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate the backtesting metrics based on ground-truth outcomes."""
    
    # 1. CRITICAL precision: CRITICAL exceptions that were RESOLVED or MISS / total CRITICAL
    critical_df = merged_df[merged_df['ai_priority'] == 'CRITICAL']
    total_critical = len(critical_df)
    
    if total_critical > 0:
        critical_correct = len(critical_df[critical_df['outcome'].isin(['RESOLVED', 'MISS'])])
        critical_precision = critical_correct / total_critical
    else:
        critical_precision = 0.0

    # 2. CRITICAL recall: CRITICAL exceptions that were RESOLVED / (RESOLVED + MISS) across ALL tiers
    # Wait, the prompt says: "CRITICAL exceptions that were RESOLVED / (RESOLVED + MISS)"
    resolved_miss_total_df = merged_df[merged_df['outcome'].isin(['RESOLVED', 'MISS'])]
    resolved_miss_total_count = len(resolved_miss_total_df)
    
    if resolved_miss_total_count > 0:
        critical_resolved_count = len(critical_df[critical_df['outcome'] == 'RESOLVED'])
        critical_recall = critical_resolved_count / resolved_miss_total_count
    else:
        critical_recall = 0.0

    # 3. False urgency rate: FALSE_ALARM / total CRITICAL + HIGH
    crit_high_df = merged_df[merged_df['ai_priority'].isin(['CRITICAL', 'HIGH'])]
    total_crit_high = len(crit_high_df)
    
    if total_crit_high > 0:
        false_alarms = len(crit_high_df[crit_high_df['outcome'] == 'FALSE_ALARM'])
        false_urgency_rate = false_alarms / total_crit_high
    else:
        false_urgency_rate = 0.0

    # 4. Priority accuracy by tier
    # Simplified accuracy measurement for the sake of backtesting
    priority_accuracy = {}
    for tier in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
        tier_df = merged_df[merged_df['ai_priority'] == tier]
        if len(tier_df) > 0:
            # Assume FALSE_ALARM means it was a bad classification (inaccurate)
            # and RESOLVED/MISS are good classifications (accurate)
            tier_accurate = len(tier_df[tier_df['outcome'].isin(['RESOLVED', 'MISS'])])
            priority_accuracy[tier] = tier_accurate / len(tier_df)
        else:
            priority_accuracy[tier] = 0.0

    return {
        "critical_precision": critical_precision,
        "critical_recall": critical_recall,
        "false_urgency_rate": false_urgency_rate,
        "priority_accuracy": priority_accuracy,
        "total_records": len(merged_df)
    }

def generate_markdown_report(metrics: Dict[str, Any], date: str, week: int, output_dir: str) -> str:
    """Generate the Markdown report into the specified output directory."""
    os.makedirs(output_dir, exist_ok=True)
    report_filename = f"backtest_{date}_W{week}.md"
    report_path = os.path.join(output_dir, report_filename)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md_content = f"""# Backtest Report — Week {week}
**Target Exception Date:** {date} | **Generated:** {timestamp}
**Total Evaluated Exceptions:** {metrics['total_records']}

---

## 1. System Performance Metrics

| Metric | Value | Description |
|---|---|---|
| **CRITICAL Precision** | {metrics['critical_precision']:.1%} | Proportion of CRITICAL alerts that were truly actionable (RESOLVED or MISS). |
| **CRITICAL Recall** | {metrics['critical_recall']:.1%} | Proportion of all true issues (RESOLVED + MISS) caught as CRITICAL. |
| **False Urgency Rate** | {metrics['false_urgency_rate']:.1%} | Proportion of CRITICAL & HIGH alerts that were FALSE_ALARM. |

---

## 2. Priority Accuracy By Tier

| Tier | Accuracy |
|---|---|
| 🔴 CRITICAL | {metrics['priority_accuracy']['CRITICAL']:.1%} |
| 🟠 HIGH | {metrics['priority_accuracy']['HIGH']:.1%} |
| 🟡 MEDIUM | {metrics['priority_accuracy']['MEDIUM']:.1%} |
| 🟢 LOW | {metrics['priority_accuracy']['LOW']:.1%} |

---
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return report_path


@click.command()
@click.option('--date', required=True, help='Target date to run backtest for (YYYY-MM-DD)')
@click.option('--week', required=True, type=int, help='Week interval for the backtest (e.g., 4 or 8)')
@click.option('--config', default='config/config.yaml', help='Path to configuration file')
@click.option('--sample', is_flag=True, help='Use sample outcomes data regardless of configuration')
def run_backtest(date, week, config, sample):
    """
    Runs the backtesting pipeline to evaluate AI triage accuracy.
    """
    logger.info(f"Starting backtest for date {date} (Week {week})")
    
    app_config = load_config(config)
    log_dir = app_config.output.log_dir
    exception_log_path = os.path.join(log_dir, "exception_log.csv")
    
    if not os.path.exists(exception_log_path):
        logger.error(f"Exception log not found at {exception_log_path}")
        sys.exit(1)

    logger.info(f"Reading exception logs from {exception_log_path}")
    try:
        exceptions_df = pd.read_csv(exception_log_path)
    except Exception as e:
        logger.error(f"Failed to read exception log: {e}")
        sys.exit(1)
        
    # Filter for the target date
    if 'exception_date' not in exceptions_df.columns:
        logger.error("Exception log missing 'exception_date' column. Using 'run_date' instead if available.")
        if 'run_date' in exceptions_df.columns:
            target_df = exceptions_df[exceptions_df['run_date'] == date]
        else:
             logger.error("No valid date column found to filter.")
             sys.exit(1)
    else:
        target_df = exceptions_df[exceptions_df['exception_date'] == date]

    if target_df.empty:
        logger.warning(f"No exceptions found for date {date} in {exception_log_path}")
        sys.exit(0)

    # Resolve Outcomes Source
    # Let's use the sample data if '--sample' is specified or if no DB config is present
    outcomes_path = "data/sample/backtest_outcomes.csv"
    if not os.path.exists(outcomes_path):
         logger.error(f"Outcome data not found at {outcomes_path}. Cannot perform backtest.")
         sys.exit(1)
         
    logger.info(f"Reading outcome data from {outcomes_path}")
    outcomes_df = pd.read_csv(outcomes_path)

    # Join on Exception ID
    logger.info("Joining target exceptions with ground-truth outcomes...")
    merged_df = target_df.merge(outcomes_df, on="exception_id", how="inner")
    
    if merged_df.empty:
         logger.warning(f"No overlapping records found between backtest outcomes and target date exceptions.")
         sys.exit(0)

    # Calculate Metrics
    logger.info("Computing metrics...")
    metrics = calculate_metrics(merged_df)
    
    # Generate Report
    backtest_output_dir = getattr(app_config, 'backtest', type('obj', (object,), {'log_dir': 'output/backtest'})).log_dir
    report_path = generate_markdown_report(metrics, date, week, backtest_output_dir)
    
    logger.info(f"Backtest complete. Report generated at {report_path}")

if __name__ == "__main__":
    run_backtest()
