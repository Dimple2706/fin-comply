-- ============================================================
-- proposed_rules — staging table for LLM-authored rule drafts
-- AI-proposed rules land here first.
-- They go live in the `rules` table ONLY after human approval.
-- ============================================================

CREATE TABLE IF NOT EXISTS proposed_rules (
    id              SERIAL          PRIMARY KEY,
    proposed_by     VARCHAR(100)    NOT NULL DEFAULT 'llm_authoring_agent',
    source_text     TEXT            NOT NULL,   -- regulatory text that was fed in
    proposed_rule   JSONB           NOT NULL,   -- full rule JSON as proposed by LLM
    field_check     JSONB,                      -- result of field_registry.check_rule_fields()
    status          VARCHAR(20)     NOT NULL
                    DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'edited')),
    reviewer        VARCHAR(100),               -- who approved/rejected
    review_notes    TEXT,                       -- reviewer comments
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,

    -- Can't mark reviewed without saying who did it
    CONSTRAINT chk_reviewer_required
        CHECK (status = 'pending' OR reviewer IS NOT NULL),

    -- Can't approve a rule with missing fields — field_check must confirm all_resolved
    CONSTRAINT chk_no_approval_with_missing_fields
        CHECK (
            status != 'approved'
            OR (field_check->>'all_resolved')::boolean = TRUE
        )
);

CREATE INDEX IF NOT EXISTS idx_proposed_rules_status
    ON proposed_rules (status);

CREATE INDEX IF NOT EXISTS idx_proposed_rules_created
    ON proposed_rules (created_at DESC);

-- Verify
SELECT 'proposed_rules table created' AS result;
