--
-- PostgreSQL database dump
--

\restrict pdvEyfDyCsXvklfMeJlfjYCbmh7cKoRYLObJguW142iRfCfbn03fJdc29dgLOZh

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: access_outcome; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.access_outcome AS ENUM (
    'granted',
    'denied'
);


ALTER TYPE public.access_outcome OWNER TO postgres;

--
-- Name: access_reason; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.access_reason AS ENUM (
    'loan_review',
    'kyc_check',
    'fraud_investigation',
    'support_query',
    'data_export'
);


ALTER TYPE public.access_reason OWNER TO postgres;

--
-- Name: account_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.account_status AS ENUM (
    'active',
    'dormant',
    'closed'
);


ALTER TYPE public.account_status OWNER TO postgres;

--
-- Name: consent_channel; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.consent_channel AS ENUM (
    'app',
    'web',
    'branch',
    'implicit',
    'pre_ticked'
);


ALTER TYPE public.consent_channel OWNER TO postgres;

--
-- Name: consent_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.consent_status AS ENUM (
    'active',
    'expired',
    'revoked',
    'withdrawn',
    'granted'
);


ALTER TYPE public.consent_status OWNER TO postgres;

--
-- Name: data_category; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.data_category AS ENUM (
    'kyc_documents',
    'transaction_history',
    'credit_score',
    'contact_info',
    'device_info'
);


ALTER TYPE public.data_category OWNER TO postgres;

--
-- Name: dsar_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.dsar_type AS ENUM (
    'access',
    'correction',
    'erasure',
    'nomination'
);


ALTER TYPE public.dsar_type OWNER TO postgres;

--
-- Name: employee_role; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.employee_role AS ENUM (
    'collections_agent',
    'underwriter',
    'customer_support',
    'data_analyst',
    'compliance_officer',
    'engineer',
    'manager'
);


ALTER TYPE public.employee_role OWNER TO postgres;

--
-- Name: encryption_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.encryption_type AS ENUM (
    'AES-256',
    'AES-128',
    'RSA-2048',
    'none',
    'md5'
);


ALTER TYPE public.encryption_type OWNER TO postgres;

--
-- Name: erasure_source; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.erasure_source AS ENUM (
    'user',
    'system'
);


ALTER TYPE public.erasure_source OWNER TO postgres;

--
-- Name: event_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.event_type AS ENUM (
    'credit_check',
    'loan_disbursal',
    'emi_collection',
    'kyc_verification',
    'marketing_push',
    'data_enrichment',
    'account_update',
    'fraud_check'
);


ALTER TYPE public.event_type OWNER TO postgres;

--
-- Name: fulfilment_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.fulfilment_status AS ENUM (
    'pending',
    'fulfilled',
    'partially_fulfilled',
    'rejected'
);


ALTER TYPE public.fulfilment_status OWNER TO postgres;

--
-- Name: kyc_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.kyc_status AS ENUM (
    'verified',
    'pending',
    'expired',
    'rejected'
);


ALTER TYPE public.kyc_status OWNER TO postgres;

--
-- Name: policy_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.policy_type_enum AS ENUM (
    'retention',
    'consent',
    'encryption',
    'access_control',
    'breach_notification'
);


ALTER TYPE public.policy_type_enum OWNER TO postgres;

--
-- Name: policy_unit_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.policy_unit_enum AS ENUM (
    'days',
    'months',
    'years',
    'hours',
    'count'
);


ALTER TYPE public.policy_unit_enum OWNER TO postgres;

--
-- Name: principal_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.principal_type AS ENUM (
    'individual',
    'minor',
    'NRI',
    'OCI',
    'PIO'
);


ALTER TYPE public.principal_type OWNER TO postgres;

--
-- Name: processing_purpose; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.processing_purpose AS ENUM (
    'loan_processing',
    'emi_collection',
    'kyc_verification',
    'credit_check',
    'marketing',
    'account_management',
    'fraud_detection',
    'data_enrichment'
);


ALTER TYPE public.processing_purpose OWNER TO postgres;

--
-- Name: processor_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.processor_type AS ENUM (
    'internal',
    'third_party_processor',
    'sub_processor'
);


ALTER TYPE public.processor_type OWNER TO postgres;

--
-- Name: retention_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.retention_status AS ENUM (
    'active',
    'expired',
    'pending_deletion',
    'deleted'
);


ALTER TYPE public.retention_status OWNER TO postgres;

--
-- Name: risk_level_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.risk_level_enum AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);


ALTER TYPE public.risk_level_enum OWNER TO postgres;

--
-- Name: system_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.system_type_enum AS ENUM (
    'crm',
    'core_banking',
    'analytics',
    'kyc_platform',
    'payment_gateway',
    'data_warehouse'
);


ALTER TYPE public.system_type_enum OWNER TO postgres;

--
-- Name: user_count_band; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.user_count_band AS ENUM (
    'minimal',
    'moderate',
    'large',
    'critical'
);


ALTER TYPE public.user_count_band OWNER TO postgres;

--
-- Name: volume_band; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.volume_band AS ENUM (
    'low',
    'medium',
    'high',
    'bulk'
);


ALTER TYPE public.volume_band OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: access_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.access_logs (
    access_hash character(12) NOT NULL,
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    employee_hash character(12) NOT NULL,
    employee_role public.employee_role NOT NULL,
    accessed_pii boolean DEFAULT false NOT NULL,
    pii_fields_accessed character varying(256),
    access_reason public.access_reason NOT NULL,
    access_outcome public.access_outcome NOT NULL,
    data_volume_accessed public.volume_band DEFAULT 'low'::public.volume_band NOT NULL,
    access_date date NOT NULL,
    system_hash character(12),
    pii_fields_justified boolean,
    CONSTRAINT chk_denied_no_pii CHECK (((access_outcome <> 'denied'::public.access_outcome) OR ((accessed_pii = false) AND (pii_fields_accessed IS NULL)))),
    CONSTRAINT chk_pii_fields_consistency CHECK (((accessed_pii = true) = ((pii_fields_accessed IS NOT NULL) AND ((pii_fields_accessed)::text <> ''::text))))
);


ALTER TABLE public.access_logs OWNER TO postgres;

--
-- Name: consent_records; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.consent_records (
    consent_hash character(12) NOT NULL,
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    consent_status public.consent_status NOT NULL,
    consent_date date NOT NULL,
    expiry_date date NOT NULL,
    withdrawal_date date,
    consented_purpose public.processing_purpose NOT NULL,
    consent_version character varying(16) NOT NULL,
    notice_provided boolean DEFAULT false NOT NULL,
    is_bundled boolean DEFAULT false NOT NULL,
    consent_channel public.consent_channel NOT NULL,
    guardian_consent_hash character(12),
    third_party_sharing_permitted boolean,
    CONSTRAINT chk_bundled_channel CHECK (((is_bundled = false) OR (consent_channel = ANY (ARRAY['implicit'::public.consent_channel, 'pre_ticked'::public.consent_channel])))),
    CONSTRAINT chk_expiry_after_consent CHECK ((expiry_date > consent_date)),
    CONSTRAINT chk_notice_channel CHECK (((notice_provided = true) OR (consent_channel = ANY (ARRAY['implicit'::public.consent_channel, 'pre_ticked'::public.consent_channel])))),
    CONSTRAINT chk_withdrawal_after_consent CHECK (((withdrawal_date IS NULL) OR (withdrawal_date >= consent_date))),
    CONSTRAINT chk_withdrawal_status CHECK (((consent_status = 'withdrawn'::public.consent_status) = (withdrawal_date IS NOT NULL)))
);


ALTER TABLE public.consent_records OWNER TO postgres;

--
-- Name: customer_master; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customer_master (
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    is_minor boolean DEFAULT false NOT NULL,
    data_principal_type public.principal_type DEFAULT 'individual'::public.principal_type NOT NULL,
    account_status public.account_status DEFAULT 'active'::public.account_status NOT NULL,
    kyc_status public.kyc_status NOT NULL,
    country character(2) DEFAULT 'IN'::bpchar NOT NULL,
    created_at date NOT NULL,
    CONSTRAINT chk_minor_type CHECK (((is_minor = false) OR (data_principal_type = 'minor'::public.principal_type))),
    CONSTRAINT chk_nri_country CHECK (((country = 'IN'::bpchar) OR (data_principal_type = ANY (ARRAY['NRI'::public.principal_type, 'OCI'::public.principal_type, 'PIO'::public.principal_type, 'individual'::public.principal_type]))))
);


ALTER TABLE public.customer_master OWNER TO postgres;

--
-- Name: data_lifecycle; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.data_lifecycle (
    lifecycle_hash character(12) NOT NULL,
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    data_category public.data_category NOT NULL,
    retention_expiry_date date NOT NULL,
    retention_status public.retention_status DEFAULT 'active'::public.retention_status NOT NULL,
    purpose_completed boolean DEFAULT false NOT NULL,
    erasure_requested boolean DEFAULT false NOT NULL,
    erasure_date date,
    legal_hold_flag boolean DEFAULT false NOT NULL,
    erasure_request_source public.erasure_source,
    CONSTRAINT chk_deleted_trigger CHECK (((retention_status <> 'deleted'::public.retention_status) OR (erasure_requested = true) OR (purpose_completed = true))),
    CONSTRAINT chk_erasure_date CHECK (((erasure_requested = true) = (erasure_date IS NOT NULL))),
    CONSTRAINT chk_erasure_source CHECK (((erasure_requested = false) OR (erasure_request_source IS NOT NULL))),
    CONSTRAINT chk_expired_not_future CHECK (((retention_status <> ALL (ARRAY['expired'::public.retention_status, 'pending_deletion'::public.retention_status, 'deleted'::public.retention_status])) OR (retention_expiry_date <= CURRENT_DATE)))
);


ALTER TABLE public.data_lifecycle OWNER TO postgres;

--
-- Name: dsar_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.dsar_requests (
    dsar_hash character(12) NOT NULL,
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    request_type public.dsar_type NOT NULL,
    submitted_date date NOT NULL,
    acknowledged_date date,
    sla_due_date date NOT NULL,
    sla_breached boolean DEFAULT false NOT NULL,
    fulfilled_date date,
    fulfillment_status public.fulfilment_status DEFAULT 'pending'::public.fulfilment_status NOT NULL,
    rejection_reason character varying(512),
    CONSTRAINT chk_fulfilled_has_date CHECK (((fulfillment_status <> 'fulfilled'::public.fulfilment_status) OR (fulfilled_date IS NOT NULL))),
    CONSTRAINT chk_pending_no_date CHECK (((fulfillment_status <> 'pending'::public.fulfilment_status) OR (fulfilled_date IS NULL))),
    CONSTRAINT chk_rejection_reason CHECK (((fulfillment_status <> 'rejected'::public.fulfilment_status) OR (rejection_reason IS NOT NULL))),
    CONSTRAINT chk_sla_breach_consistent CHECK (((sla_breached = false) OR ((fulfilled_date IS NULL) OR (fulfilled_date > sla_due_date)) OR ((fulfilled_date IS NULL) AND (CURRENT_DATE > sla_due_date)))),
    CONSTRAINT chk_sla_is_30_days CHECK ((sla_due_date = (submitted_date + '30 days'::interval)))
);


ALTER TABLE public.dsar_requests OWNER TO postgres;

--
-- Name: governance_config; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.governance_config (
    tenant_id character varying(32) NOT NULL,
    tenant_name character varying(128) NOT NULL,
    grievance_endpoint_available boolean DEFAULT false NOT NULL,
    dpo_assigned boolean DEFAULT false NOT NULL,
    dpo_contact_masked character varying(64),
    audit_frequency_days integer NOT NULL,
    last_audit_date date,
    risk_level public.risk_level_enum DEFAULT 'MEDIUM'::public.risk_level_enum NOT NULL,
    CONSTRAINT chk_dpo_contact CHECK (((dpo_assigned = false) OR (dpo_contact_masked IS NOT NULL))),
    CONSTRAINT governance_config_audit_frequency_days_check CHECK ((audit_frequency_days > 0))
);


ALTER TABLE public.governance_config OWNER TO postgres;

--
-- Name: TABLE governance_config; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.governance_config IS 'Tenant-level governance state. One row per client. Anchor for all FK references to tenant_id.';


--
-- Name: COLUMN governance_config.dpo_contact_masked; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.governance_config.dpo_contact_masked IS 'Masked to first character + domain only. Full email not stored in redacted DB.';


--
-- Name: COLUMN governance_config.audit_frequency_days; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.governance_config.audit_frequency_days IS 'Machine-readable audit cadence. Used by Audit Agent DPDP-012 to detect overdue audits.';


--
-- Name: policies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.policies (
    policy_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    policy_type public.policy_type_enum NOT NULL,
    policy_name character varying(128) NOT NULL,
    policy_value_numeric integer,
    policy_value_unit public.policy_unit_enum,
    policy_value_text character varying(512),
    effective_date date NOT NULL,
    last_updated date NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT chk_last_updated_after_effective CHECK ((last_updated >= effective_date)),
    CONSTRAINT chk_numeric_has_unit CHECK (((policy_value_numeric IS NULL) OR (policy_value_unit IS NOT NULL)))
);


ALTER TABLE public.policies OWNER TO postgres;

--
-- Name: security_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.security_events (
    security_hash character(12) NOT NULL,
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    pii_encrypted boolean DEFAULT true NOT NULL,
    encryption_type public.encryption_type NOT NULL,
    breach_detected boolean DEFAULT false NOT NULL,
    breach_confirmed_date date,
    notification_delay_hours integer,
    affected_user_count public.user_count_band,
    data_categories_breached character varying(512),
    security_audit_flag boolean DEFAULT false NOT NULL,
    CONSTRAINT chk_breach_fields CHECK (((breach_detected = false) OR ((breach_confirmed_date IS NOT NULL) AND (notification_delay_hours IS NOT NULL) AND (affected_user_count IS NOT NULL)))),
    CONSTRAINT chk_encryption_consistency CHECK (((pii_encrypted = true) = (encryption_type = ANY (ARRAY['AES-256'::public.encryption_type, 'AES-128'::public.encryption_type, 'RSA-2048'::public.encryption_type])))),
    CONSTRAINT chk_no_breach_no_delay CHECK (((breach_detected = true) OR ((breach_confirmed_date IS NULL) AND (notification_delay_hours IS NULL)))),
    CONSTRAINT security_events_notification_delay_hours_check CHECK ((notification_delay_hours >= 0))
);


ALTER TABLE public.security_events OWNER TO postgres;

--
-- Name: system_inventory; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.system_inventory (
    system_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    system_name character varying(128) NOT NULL,
    system_type public.system_type_enum NOT NULL,
    pii_stored boolean DEFAULT false NOT NULL,
    encryption_enabled boolean DEFAULT false NOT NULL,
    access_control_enabled boolean DEFAULT false NOT NULL,
    retention_policy_applied boolean DEFAULT false NOT NULL,
    data_processor_type public.processor_type DEFAULT 'internal'::public.processor_type NOT NULL,
    dpa_signed boolean DEFAULT false NOT NULL,
    dpa_expiry_date date,
    third_party_integrations character varying(256),
    CONSTRAINT chk_dpa_expiry_requires_signed CHECK (((dpa_expiry_date IS NULL) OR (dpa_signed = true))),
    CONSTRAINT chk_dpa_only_third_party CHECK (((data_processor_type = 'internal'::public.processor_type) OR (dpa_expiry_date IS NOT NULL) OR (dpa_signed = false))),
    CONSTRAINT chk_internal_no_dpa_expiry CHECK (((data_processor_type <> 'internal'::public.processor_type) OR (dpa_expiry_date IS NULL)))
);


ALTER TABLE public.system_inventory OWNER TO postgres;

--
-- Name: transaction_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_events (
    event_hash character(12) NOT NULL,
    customer_hash character(12) NOT NULL,
    tenant_id character varying(32) NOT NULL,
    consent_hash character(12),
    event_type public.event_type NOT NULL,
    processing_purpose public.processing_purpose NOT NULL,
    event_date date NOT NULL,
    shared_with_third_party boolean DEFAULT false NOT NULL,
    third_party_hash character(12),
    is_cross_border boolean DEFAULT false NOT NULL,
    transfer_country character(2),
    CONSTRAINT chk_cross_border_country CHECK (((is_cross_border = false) OR (transfer_country IS NOT NULL))),
    CONSTRAINT chk_domestic_no_country CHECK (((is_cross_border = true) OR (transfer_country IS NULL))),
    CONSTRAINT chk_third_party_id CHECK (((shared_with_third_party = false) OR (third_party_hash IS NOT NULL)))
);


ALTER TABLE public.transaction_events OWNER TO postgres;

--
-- Name: access_logs access_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.access_logs
    ADD CONSTRAINT access_logs_pkey PRIMARY KEY (access_hash);


--
-- Name: consent_records consent_records_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consent_records
    ADD CONSTRAINT consent_records_pkey PRIMARY KEY (consent_hash);


--
-- Name: customer_master customer_master_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_master
    ADD CONSTRAINT customer_master_pkey PRIMARY KEY (customer_hash);


--
-- Name: data_lifecycle data_lifecycle_customer_hash_data_category_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.data_lifecycle
    ADD CONSTRAINT data_lifecycle_customer_hash_data_category_key UNIQUE (customer_hash, data_category);


--
-- Name: data_lifecycle data_lifecycle_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.data_lifecycle
    ADD CONSTRAINT data_lifecycle_pkey PRIMARY KEY (lifecycle_hash);


--
-- Name: dsar_requests dsar_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dsar_requests
    ADD CONSTRAINT dsar_requests_pkey PRIMARY KEY (dsar_hash);


--
-- Name: governance_config governance_config_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.governance_config
    ADD CONSTRAINT governance_config_pkey PRIMARY KEY (tenant_id);


--
-- Name: policies policies_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (policy_hash);


--
-- Name: security_events security_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.security_events
    ADD CONSTRAINT security_events_pkey PRIMARY KEY (security_hash);


--
-- Name: system_inventory system_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_inventory
    ADD CONSTRAINT system_inventory_pkey PRIMARY KEY (system_hash);


--
-- Name: transaction_events transaction_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_events
    ADD CONSTRAINT transaction_events_pkey PRIMARY KEY (event_hash);


--
-- Name: access_logs access_logs_customer_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.access_logs
    ADD CONSTRAINT access_logs_customer_hash_fkey FOREIGN KEY (customer_hash) REFERENCES public.customer_master(customer_hash);


--
-- Name: access_logs access_logs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.access_logs
    ADD CONSTRAINT access_logs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: consent_records consent_records_customer_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consent_records
    ADD CONSTRAINT consent_records_customer_hash_fkey FOREIGN KEY (customer_hash) REFERENCES public.customer_master(customer_hash);


--
-- Name: consent_records consent_records_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consent_records
    ADD CONSTRAINT consent_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: customer_master customer_master_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_master
    ADD CONSTRAINT customer_master_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: data_lifecycle data_lifecycle_customer_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.data_lifecycle
    ADD CONSTRAINT data_lifecycle_customer_hash_fkey FOREIGN KEY (customer_hash) REFERENCES public.customer_master(customer_hash);


--
-- Name: data_lifecycle data_lifecycle_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.data_lifecycle
    ADD CONSTRAINT data_lifecycle_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: dsar_requests dsar_requests_customer_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dsar_requests
    ADD CONSTRAINT dsar_requests_customer_hash_fkey FOREIGN KEY (customer_hash) REFERENCES public.customer_master(customer_hash);


--
-- Name: dsar_requests dsar_requests_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dsar_requests
    ADD CONSTRAINT dsar_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: policies policies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: security_events security_events_customer_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.security_events
    ADD CONSTRAINT security_events_customer_hash_fkey FOREIGN KEY (customer_hash) REFERENCES public.customer_master(customer_hash);


--
-- Name: security_events security_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.security_events
    ADD CONSTRAINT security_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: system_inventory system_inventory_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_inventory
    ADD CONSTRAINT system_inventory_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: transaction_events transaction_events_consent_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_events
    ADD CONSTRAINT transaction_events_consent_hash_fkey FOREIGN KEY (consent_hash) REFERENCES public.consent_records(consent_hash);


--
-- Name: transaction_events transaction_events_customer_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_events
    ADD CONSTRAINT transaction_events_customer_hash_fkey FOREIGN KEY (customer_hash) REFERENCES public.customer_master(customer_hash);


--
-- Name: transaction_events transaction_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_events
    ADD CONSTRAINT transaction_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.governance_config(tenant_id);


--
-- Name: transaction_events transaction_events_third_party_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_events
    ADD CONSTRAINT transaction_events_third_party_hash_fkey FOREIGN KEY (third_party_hash) REFERENCES public.system_inventory(system_hash);


--
-- Name: evaluation_results; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE IF NOT EXISTS public.evaluation_results (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id character varying(32) NOT NULL,
    result_json jsonb NOT NULL,
    risk_score numeric(5,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.evaluation_results OWNER TO postgres;


--
-- Name: idx_evaluation_results_tenant_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX IF NOT EXISTS idx_evaluation_results_tenant_id ON public.evaluation_results USING btree (tenant_id);


--
-- Name: idx_evaluation_results_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX IF NOT EXISTS idx_evaluation_results_created_at ON public.evaluation_results USING btree (created_at DESC);


--
-- PostgreSQL database dump complete
--

\unrestrict pdvEyfDyCsXvklfMeJlfjYCbmh7cKoRYLObJguW142iRfCfbn03fJdc29dgLOZh