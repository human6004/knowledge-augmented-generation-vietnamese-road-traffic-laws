ALTER TABLE chat_messages ADD COLUMN feedback VARCHAR(20);
ALTER TABLE chat_messages ADD COLUMN feedback_note VARCHAR(1000);
ALTER TABLE chat_messages ADD COLUMN resolved BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chat_messages ADD COLUMN resolution VARCHAR(1000);
CREATE TABLE content_history (
 id BINARY(16) PRIMARY KEY, content_id BINARY(16) NOT NULL, content_version BIGINT NOT NULL,
 data LONGTEXT NOT NULL, published BOOLEAN NOT NULL, changed_at DATETIME(6) NOT NULL,
 FOREIGN KEY(content_id) REFERENCES content(id)
);
CREATE INDEX history_content ON content_history(content_id, changed_at);
CREATE TABLE law_relations (
 id BINARY(16) PRIMARY KEY, predecessor BINARY(16) NOT NULL, successor BINARY(16) NOT NULL,
 relation_type VARCHAR(20) NOT NULL CHECK(relation_type IN ('REPLACES','AMENDS')), effective_date DATE NOT NULL,
 note VARCHAR(1000) NOT NULL, version BIGINT NOT NULL DEFAULT 0, UNIQUE(predecessor, successor, relation_type), CHECK(predecessor <> successor),
 FOREIGN KEY(predecessor) REFERENCES content(id), FOREIGN KEY(successor) REFERENCES content(id)
);
CREATE TABLE penalty_rules (
 id BINARY(16) PRIMARY KEY, document_id BINARY(16) NOT NULL, data LONGTEXT NOT NULL,
 published BOOLEAN NOT NULL DEFAULT FALSE, version BIGINT NOT NULL DEFAULT 0,
 FOREIGN KEY(document_id) REFERENCES content(id)
);
