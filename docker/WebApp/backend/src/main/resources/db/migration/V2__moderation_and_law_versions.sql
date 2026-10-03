ALTER TABLE chat_messages ADD COLUMN feedback VARCHAR(20);
ALTER TABLE chat_messages ADD COLUMN feedback_note VARCHAR(1000);
ALTER TABLE chat_messages ADD COLUMN resolved BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chat_messages ADD COLUMN resolution VARCHAR(1000);
CREATE TABLE content_history (
 id UUID PRIMARY KEY, content_id UUID NOT NULL REFERENCES content(id), content_version BIGINT NOT NULL,
 data TEXT NOT NULL, published BOOLEAN NOT NULL, changed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX history_content ON content_history(content_id, changed_at);
CREATE TABLE law_relations (
 id UUID PRIMARY KEY, predecessor UUID NOT NULL REFERENCES content(id), successor UUID NOT NULL REFERENCES content(id),
 relation_type VARCHAR(20) NOT NULL CHECK(relation_type IN ('REPLACES','AMENDS')), effective_date DATE NOT NULL,
 note VARCHAR(1000) NOT NULL, version BIGINT NOT NULL DEFAULT 0, UNIQUE(predecessor, successor, relation_type), CHECK(predecessor <> successor)
);
CREATE TABLE penalty_rules (
 id UUID PRIMARY KEY, document_id UUID NOT NULL REFERENCES content(id), data TEXT NOT NULL,
 published BOOLEAN NOT NULL DEFAULT FALSE, version BIGINT NOT NULL DEFAULT 0
);
