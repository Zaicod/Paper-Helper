CREATE TABLE pf_research_tasks (
    task_id VARCHAR(36) PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    idempotency_key VARCHAR(36) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    topic VARCHAR(500) NOT NULL,
    status VARCHAR(16) NOT NULL,
    payload_json MEDIUMTEXT NOT NULL,
    events_json MEDIUMTEXT NOT NULL,
    report_json LONGTEXT,
    error_code VARCHAR(64),
    error_message VARCHAR(1000),
    sync_error VARCHAR(1000),
    created_at TIMESTAMP(6) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL,
    deadline_at TIMESTAMP(6) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT fk_pf_task_owner FOREIGN KEY (owner_id) REFERENCES pf_users(id),
    CONSTRAINT uq_pf_task_request UNIQUE (owner_id, idempotency_key)
);
CREATE INDEX ix_pf_task_owner ON pf_research_tasks(owner_id, created_at);
CREATE INDEX ix_pf_task_status ON pf_research_tasks(status, updated_at);
