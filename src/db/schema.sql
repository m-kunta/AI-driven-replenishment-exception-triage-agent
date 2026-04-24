CREATE TABLE IF NOT EXISTS analyst_overrides (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_id                        TEXT    NOT NULL,
    run_date                            TEXT    NOT NULL,
    analyst_username                    TEXT    NOT NULL,
    submitted_at                        TEXT    NOT NULL,

    -- Corrected output fields (at least one must be non-null at insert time)
    override_priority                   TEXT,
    override_root_cause                 TEXT,
    override_recommended_action         TEXT,
    override_financial_impact_statement TEXT,
    override_planner_brief              TEXT,
    override_compounding_risks          TEXT,
    analyst_note                        TEXT,

    -- Full EnrichedExceptionSchema snapshot (model_dump(mode='json') serialized)
    enriched_input_snapshot             TEXT    NOT NULL,

    -- Approval workflow
    approval_status                     TEXT    NOT NULL DEFAULT 'pending'
                                                CHECK (approval_status IN ('pending','approved','rejected')),
    approved_by                         TEXT,
    approved_at                         TEXT,
    auto_approved                       INTEGER NOT NULL DEFAULT 0,
    rejected_by                         TEXT,
    rejected_at                         TEXT,
    rejection_reason                    TEXT
);

CREATE INDEX IF NOT EXISTS idx_overrides_exception_id
    ON analyst_overrides (exception_id);

CREATE INDEX IF NOT EXISTS idx_overrides_run_date
    ON analyst_overrides (run_date);

CREATE INDEX IF NOT EXISTS idx_overrides_approval_status_submitted
    ON analyst_overrides (approval_status, submitted_at);

CREATE TABLE IF NOT EXISTS action_records (
    request_id                          TEXT PRIMARY KEY,
    exception_id                        TEXT NOT NULL,
    run_date                            TEXT NOT NULL,
    action_type                         TEXT NOT NULL,
    requested_by                        TEXT NOT NULL,
    requested_by_role                   TEXT NOT NULL,
    payload                             TEXT NOT NULL,
    status                              TEXT NOT NULL DEFAULT 'queued'
                                        CHECK (status IN ('queued','sent','failed','completed')),
    created_at                          TEXT NOT NULL,
    updated_at                          TEXT NOT NULL,
    failure_reason                      TEXT,
    downstream_response                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_actions_exception_id
    ON action_records (exception_id);
