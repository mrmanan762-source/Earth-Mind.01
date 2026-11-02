-- ==============================================================================
-- EarthMind Memory Module: Level 3 Supabase PostgreSQL Schema Migration
-- Specification: Memory Module Architecture Specification v1.0
-- Migration: 001_create_memory_records.sql
-- ==============================================================================

CREATE TABLE IF NOT EXISTS memory_records (
    record_id VARCHAR(64) PRIMARY KEY,
    domain VARCHAR(32) NOT NULL,
    record_type VARCHAR(64) NOT NULL,
    owner_id VARCHAR(128),
    scope_type VARCHAR(32) NOT NULL,
    scope_id VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL,
    source VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    schema_version VARCHAR(32) NOT NULL DEFAULT '1.0',
    record_version INT NOT NULL DEFAULT 1,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    retention_policy_id VARCHAR(64),
    expires_at TIMESTAMPTZ,
    classification VARCHAR(64) NOT NULL,
    correlation_id VARCHAR(128),

    -- Domain constraint: USER or GENERAL
    CONSTRAINT chk_memory_domain CHECK (domain IN ('USER', 'GENERAL')),

    -- Scope type constraint: all 6 approved scopes
    CONSTRAINT chk_memory_scope_type CHECK (
        scope_type IN ('USER', 'CONVERSATION', 'FARM', 'FIELD', 'CROP_CYCLE', 'GENERAL')
    ),

    -- Status constraint: all 5 approved statuses
    CONSTRAINT chk_memory_status CHECK (
        status IN ('ACTIVE', 'ARCHIVED', 'DELETED', 'EXPIRED', 'PENDING')
    ),

    -- Positive record version for optimistic locking
    CONSTRAINT chk_memory_record_version CHECK (record_version >= 1),

    -- Expiration validity
    CONSTRAINT chk_memory_expiration CHECK (expires_at IS NULL OR expires_at > created_at),

    -- Domain & Ownership integrity:
    -- USER domain MUST have a non-empty owner_id and cannot have GENERAL scope.
    -- GENERAL domain MUST NOT have an owner_id (NULL) and cannot have USER scope.
    CONSTRAINT chk_memory_domain_ownership CHECK (
        (domain = 'USER' AND owner_id IS NOT NULL AND TRIM(owner_id) != '' AND scope_type != 'GENERAL')
        OR
        (domain = 'GENERAL' AND owner_id IS NULL AND scope_type != 'USER')
    )
);

-- Indexes for efficient structured retrieval and querying patterns
CREATE INDEX IF NOT EXISTS idx_memory_records_owner_domain
    ON memory_records (owner_id, domain)
    WHERE status != 'DELETED';

CREATE INDEX IF NOT EXISTS idx_memory_records_scope
    ON memory_records (scope_type, scope_id);

CREATE INDEX IF NOT EXISTS idx_memory_records_record_type
    ON memory_records (record_type);

CREATE INDEX IF NOT EXISTS idx_memory_records_status
    ON memory_records (status);

CREATE INDEX IF NOT EXISTS idx_memory_records_correlation_id
    ON memory_records (correlation_id)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_records_expires_at
    ON memory_records (expires_at)
    WHERE expires_at IS NOT NULL;
