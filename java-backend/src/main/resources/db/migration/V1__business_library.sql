CREATE TABLE pf_users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    username_normalized VARCHAR(64) NOT NULL,
    email VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT uq_pf_username UNIQUE (username_normalized),
    CONSTRAINT uq_pf_email UNIQUE (email_normalized)
);

CREATE TABLE pf_collections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_normalized VARCHAR(255) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    overall_note MEDIUMTEXT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT fk_pf_collection_owner FOREIGN KEY (owner_id) REFERENCES pf_users(id),
    CONSTRAINT uq_pf_collection_owner_name UNIQUE (owner_id, name_normalized)
);
CREATE INDEX ix_pf_collection_owner ON pf_collections(owner_id);

CREATE TABLE pf_papers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    title VARCHAR(1024) NOT NULL,
    abstract_text TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    published VARCHAR(64),
    page_url VARCHAR(2048) NOT NULL,
    pdf_url VARCHAR(2048),
    created_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT uq_pf_paper_source_id UNIQUE (source, external_id)
);

CREATE TABLE pf_collection_papers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_id BIGINT NOT NULL,
    paper_id BIGINT NOT NULL,
    note MEDIUMTEXT NOT NULL,
    added_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT fk_pf_link_collection FOREIGN KEY (collection_id) REFERENCES pf_collections(id) ON DELETE CASCADE,
    CONSTRAINT fk_pf_link_paper FOREIGN KEY (paper_id) REFERENCES pf_papers(id),
    CONSTRAINT uq_pf_collection_paper UNIQUE (collection_id, paper_id)
);
