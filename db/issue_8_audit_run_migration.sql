-- Issue 8: Immutable Audit Run Migration

CREATE TABLE IF NOT EXISTS public.audit_runs (
    audit_run_id character varying(64) PRIMARY KEY,
    tenant_id character varying(32) NOT NULL,
    input_snapshot_hash character varying(64) NOT NULL,
    rule_set_hash character varying(64) NOT NULL,
    clause_set_hash character varying(64) NOT NULL,
    engine_version character varying(32) NOT NULL,
    model_hash character varying(64),
    source_data_row_counts jsonb,
    validation_summary jsonb,
    status character varying(32) NOT NULL, -- completed, failed, not_assessable
    parent_audit_run_id character varying(64),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.evaluation_results ADD COLUMN IF NOT EXISTS audit_run_id character varying(64);
CREATE INDEX IF NOT EXISTS idx_evaluation_results_audit_run_id ON public.evaluation_results (audit_run_id);
