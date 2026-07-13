-- ============================================================
-- DPDP Compliance Checker — Rules & Clauses Tables
-- Run this ONCE against your existing Postgres DB
-- Order: clauses first (rules has FK → clauses)
-- ============================================================

-- Severity enum (reuse if already defined in your schema)
DO $$ BEGIN
    CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Agent enum
DO $$ BEGIN
    CREATE TYPE agent_name AS ENUM (
        'regulation_agent',
        'audit_agent',
        'risk_agent',
        'policy_agent',
        'reporting_agent'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Penalty tier enum
DO $$ BEGIN
    CREATE TYPE penalty_tier AS ENUM ('TIER_1', 'TIER_2', 'TIER_3');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 1. CLAUSES TABLE
-- Stores legal text, signal mappings, and penalty tiers.
-- Source: clauses.json
-- ============================================================
CREATE TABLE IF NOT EXISTS clauses (
    clause_id               VARCHAR(20)     PRIMARY KEY,         -- e.g. "DPDP-001"
    legal_title             TEXT            NOT NULL,
    dpdp_section            JSONB           NOT NULL,            -- array: ["Section 6(1)", "Section 5"]
    legal_text              TEXT            NOT NULL,
    plain_english_obligation TEXT           NOT NULL,
    severity_weight         NUMERIC(4,3)    NOT NULL             -- 0.0 – 1.0
                            CHECK (severity_weight BETWEEN 0 AND 1),
    evidence_required       JSONB           NOT NULL,            -- array of field name strings
    signal_mapping          JSONB           NOT NULL,            -- object: {"S1": "...", "S2": "..."}
    penalty_tier            penalty_tier    NOT NULL,
    max_penalty_crore       INTEGER         NOT NULL,
    keywords                JSONB           NOT NULL,            -- array of strings
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

-- ============================================================
-- 2. RULES TABLE
-- Stores rule definitions, evidence signals, thresholds.
-- Source: dpdp_rules.json
-- This replaces the static JSON file — agents query this table
-- at runtime. No rule logic lives in Python anymore.
-- ============================================================
CREATE TABLE IF NOT EXISTS rules (
    rule_id                 VARCHAR(20)     PRIMARY KEY,         -- e.g. "DPDP-001"
    clause_id               VARCHAR(20)     NOT NULL
                            REFERENCES clauses(clause_id)
                            ON DELETE RESTRICT,                  -- never silently delete a clause a rule depends on
    rule_name               TEXT            NOT NULL,
    dpdp_section            VARCHAR(50)     NOT NULL,            -- e.g. "Section 6(1)"
    description             TEXT            NOT NULL,
    severity                severity_level  NOT NULL,
    risk_weight             NUMERIC(4,3)    NOT NULL
                            CHECK (risk_weight BETWEEN 0 AND 1),
    check_type              VARCHAR(50)     NOT NULL
                            DEFAULT 'weighted_evidence',
    assigned_agent          agent_name      NOT NULL,
    primary_table           VARCHAR(100)    NOT NULL,            -- table the main query runs against
    join_tables             JSONB           NOT NULL             -- array of table names (can be empty [])
                            DEFAULT '[]',
    join_key                VARCHAR(100),                        -- nullable — not all rules join
    evidence_signals        JSONB           NOT NULL,            -- array of signal objects (full definition)
    violation_threshold     NUMERIC(4,3)    NOT NULL
                            CHECK (violation_threshold BETWEEN 0 AND 1),
    risk_threshold          NUMERIC(4,3)    NOT NULL
                            CHECK (risk_threshold BETWEEN 0 AND 1),
    recurrence_bonus        NUMERIC(4,3)    NOT NULL
                            DEFAULT 0.0
                            CHECK (recurrence_bonus BETWEEN 0 AND 1),
    -- Dynamic rule lifecycle fields (new — not in original JSON)
    enabled                 BOOLEAN         NOT NULL DEFAULT TRUE,
    version                 INTEGER         NOT NULL DEFAULT 1,
    effective_date          DATE            NOT NULL DEFAULT CURRENT_DATE,
    approved_by             VARCHAR(100),                        -- reviewer name/ID (NULL = seeded from JSON)
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW(),
    -- Constraint: signal weights inside evidence_signals must sum to ~1.0
    -- (enforced in application layer, not SQL — JSONB aggregation not feasible in CHECK)
    CONSTRAINT rule_thresholds_ordered
        CHECK (risk_threshold < violation_threshold)            -- warning always fires before violation
);

-- Index agents use at runtime: "give me all active rules for regulation_agent"
CREATE INDEX IF NOT EXISTS idx_rules_agent_enabled
    ON rules (assigned_agent, enabled);

-- Index for rule lifecycle queries: "show all versions of DPDP-001"
CREATE INDEX IF NOT EXISTS idx_rules_clause
    ON rules (clause_id);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_rules_updated_at ON rules;
CREATE TRIGGER trg_rules_updated_at
    BEFORE UPDATE ON rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_clauses_updated_at ON clauses;
CREATE TRIGGER trg_clauses_updated_at
    BEFORE UPDATE ON clauses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
