CREATE TABLE accounts (
 id BINARY(16) PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE, password VARCHAR(100) NOT NULL,
 name VARCHAR(100) NOT NULL, role VARCHAR(10) NOT NULL CHECK(role IN ('USER','ADMIN')),
 enabled BOOLEAN NOT NULL DEFAULT TRUE, token_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE content (
 id BINARY(16) PRIMARY KEY, kind VARCHAR(20) NOT NULL CHECK(kind IN ('questions','signs','documents')),
 external_id VARCHAR(250) NOT NULL, data LONGTEXT NOT NULL, published BOOLEAN NOT NULL DEFAULT FALSE,
 version BIGINT NOT NULL DEFAULT 0, UNIQUE(kind, external_id)
);
CREATE TABLE exams (
 id BINARY(16) PRIMARY KEY, owner_id BINARY(16) NOT NULL, started_at DATETIME(6) NOT NULL,
 expires_at DATETIME(6) NOT NULL, submitted_at DATETIME(6),
 snapshot LONGTEXT NOT NULL, answers LONGTEXT NOT NULL, score INTEGER, critical_failed BOOLEAN, passed BOOLEAN,
 FOREIGN KEY(owner_id) REFERENCES accounts(id)
);
CREATE INDEX exams_owner ON exams(owner_id, started_at);
CREATE TABLE study_attempts (
 id BINARY(16) PRIMARY KEY, owner_id BINARY(16) NOT NULL, question_id BINARY(16) NOT NULL,
 chapter INTEGER NOT NULL, correct BOOLEAN NOT NULL, created_at DATETIME(6) NOT NULL,
 FOREIGN KEY(owner_id) REFERENCES accounts(id), FOREIGN KEY(question_id) REFERENCES content(id)
);
CREATE INDEX study_owner ON study_attempts(owner_id, chapter);
CREATE TABLE chat_messages (
 id BINARY(16) PRIMARY KEY, owner_id BINARY(16) NOT NULL, question LONGTEXT NOT NULL,
 answer LONGTEXT, citations LONGTEXT NOT NULL, state VARCHAR(20) NOT NULL, created_at DATETIME(6) NOT NULL,
 FOREIGN KEY(owner_id) REFERENCES accounts(id)
);
CREATE INDEX chat_owner ON chat_messages(owner_id, created_at);
