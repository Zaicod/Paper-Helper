ALTER TABLE pf_collection_papers ADD COLUMN metadata_json MEDIUMTEXT NULL;
ALTER TABLE pf_collection_papers ADD COLUMN metadata_edited BOOLEAN NOT NULL DEFAULT FALSE;
