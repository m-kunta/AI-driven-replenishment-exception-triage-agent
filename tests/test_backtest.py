import os
import pytest
import pandas as pd
from scripts.run_backtest import calculate_metrics, generate_markdown_report

def test_calculate_metrics():
    # Setup test dataframe
    data = {
        'exception_id': ['id1', 'id2', 'id3', 'id4', 'id5'],
        'ai_priority': ['CRITICAL', 'CRITICAL', 'HIGH', 'HIGH', 'LOW'],
        'outcome': ['RESOLVED', 'MISS', 'FALSE_ALARM', 'RESOLVED', 'FALSE_ALARM']
    }
    df = pd.DataFrame(data)

    metrics = calculate_metrics(df)

    # 1. CRITICAL precision: 2 CRITICAL total. 1 RESOLVED, 1 MISS. Both are "correct". 2/2 = 1.0 (100%)
    assert metrics['critical_precision'] == 1.0

    # 2. CRITICAL recall: 3 ground truth issues total (id1, id2, id4). 
    # CRITICAL correctly caught 1 of them (id1) that was resolved. 1 / 3 = 0.33...
    assert metrics['critical_recall'] == pytest.approx(1/3)

    # 3. False urgency rate: CRITICAL + HIGH = 4. 
    # id3 is FALSE_ALARM and HIGH. 1 / 4 = 0.25 (25%)
    assert metrics['false_urgency_rate'] == 0.25

    # 4. Priority Accuracy
    # CRITICAL: 2 total, 2 correct = 1.0
    # HIGH: 2 total, 1 correct (id4) = 0.5
    # MEDIUM: 0 total = 0.0
    # LOW: 1 total, 0 correct (id5) = 0.0
    assert metrics['priority_accuracy']['CRITICAL'] == 1.0
    assert metrics['priority_accuracy']['HIGH'] == 0.5
    assert metrics['priority_accuracy']['MEDIUM'] == 0.0
    assert metrics['priority_accuracy']['LOW'] == 0.0

def test_generate_markdown_report_success(tmp_path):
    # Setup metrics
    metrics = {
        "critical_precision": 0.5,
        "critical_recall": 0.75,
        "false_urgency_rate": 0.1,
        "priority_accuracy": {
            "CRITICAL": 0.8,
            "HIGH": 0.6,
            "MEDIUM": 0.4,
            "LOW": 0.9
        },
        "total_records": 100
    }
    date = "2026-03-01"
    week = 4
    output_dir = str(tmp_path / "backtest")
    
    report_path = generate_markdown_report(metrics, date, week, output_dir)
    
    assert os.path.exists(report_path)
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify content in report
    assert "Backtest Report — Week 4" in content
    assert "**Target Exception Date:** 2026-03-01" in content
    assert "100" in content
    assert "50.0%" in content  # precision 0.5 -> 50.0%
    assert "75.0%" in content  # recall 0.75 -> 75.0%
