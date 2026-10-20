CREATE TABLE pf_model_settings (
 owner_id BIGINT NOT NULL,
 provider VARCHAR(16) NOT NULL,
 model VARCHAR(128) NOT NULL,
 key_ciphertext TEXT,
 key_hint VARCHAR(24),
 PRIMARY KEY(owner_id,provider),
 CONSTRAINT fk_pf_model_owner FOREIGN KEY(owner_id) REFERENCES pf_users(id)
);
CREATE TABLE pf_model_defaults (
 owner_id BIGINT PRIMARY KEY,
 provider VARCHAR(16),
 CONSTRAINT fk_pf_model_default_owner FOREIGN KEY(owner_id) REFERENCES pf_users(id)
);
