CREATE TABLE legal_units (
 id BINARY(16) PRIMARY KEY,
 document_id BINARY(16) NOT NULL,
 unit_id VARCHAR(500) NOT NULL UNIQUE,
 data LONGTEXT NOT NULL,
 published BOOLEAN NOT NULL DEFAULT FALSE,
 version BIGINT NOT NULL DEFAULT 0,
 FOREIGN KEY(document_id) REFERENCES content(id)
);
CREATE INDEX units_document ON legal_units(document_id);
