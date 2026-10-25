
CREATE TABLE IF NOT EXISTS task_evidence (
    id BIGSERIAL PRIMARY KEY,

    tenant_id VARCHAR(32) NOT NULL,
    audit_run_id VARCHAR(64) NOT NULL,

    rule_id VARCHAR(50) NOT NULL,
    signal_id VARCHAR(50) NOT NULL,

    affected_records_count INTEGER NOT NULL DEFAULT 0
        CHECK (affected_records_count >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_task_evidence_run_signal
        UNIQUE (tenant_id, audit_run_id, rule_id, signal_id),

    CONSTRAINT fk_task_evidence_audit_run
        FOREIGN KEY (audit_run_id)
        REFERENCES audit_runs(audit_run_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_task_evidence_template
        FOREIGN KEY (rule_id, signal_id)
        REFERENCES task_templates(rule_id, signal_id)
);

CREATE INDEX IF NOT EXISTS idx_task_evidence_tenant_run
    ON task_evidence(tenant_id, audit_run_id);

CREATE INDEX IF NOT EXISTS idx_task_evidence_rule_signal
    ON task_evidence(rule_id, signal_id);
