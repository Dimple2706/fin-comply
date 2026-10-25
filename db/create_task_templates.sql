-- Task Assessment & Assignment Module
-- Stores remediation templates mapped to compliance rule signals.

CREATE TABLE IF NOT EXISTS task_templates (
    id BIGSERIAL PRIMARY KEY,

    rule_id VARCHAR(50) NOT NULL,
    signal_id VARCHAR(50) NOT NULL,

    task_title VARCHAR(255) NOT NULL,
    task_description TEXT NOT NULL,

    responsible_team VARCHAR(150) NOT NULL,

    priority VARCHAR(20) NOT NULL
        CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),

    remediation_steps JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_task_rule_signal
        UNIQUE (rule_id, signal_id),

    CONSTRAINT fk_task_rule
        FOREIGN KEY (rule_id)
        REFERENCES rules(rule_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_remediation_steps_array
        CHECK (jsonb_typeof(remediation_steps) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_task_templates_rule
ON task_templates(rule_id);

CREATE INDEX IF NOT EXISTS idx_task_templates_team
ON task_templates(responsible_team);

CREATE INDEX IF NOT EXISTS idx_task_templates_active
ON task_templates(is_active);