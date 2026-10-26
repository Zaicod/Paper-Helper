CREATE TABLE pf_paper_documents (
 record_id VARCHAR(36) PRIMARY KEY,
 owner_id BIGINT NOT NULL,
 collection_id BIGINT NOT NULL,
 paper_id BIGINT NOT NULL,
 metadata_hash VARCHAR(64) NOT NULL,
 document_id VARCHAR(36),
 status_json MEDIUMTEXT NOT NULL,
 created_at TIMESTAMP(6) NOT NULL,
 CONSTRAINT fk_pf_document_owner FOREIGN KEY (owner_id) REFERENCES pf_users(id)
);
CREATE INDEX ix_pf_document_paper ON pf_paper_documents(owner_id,collection_id,paper_id,created_at);
CREATE INDEX ix_pf_document_file ON pf_paper_documents(owner_id,document_id);
