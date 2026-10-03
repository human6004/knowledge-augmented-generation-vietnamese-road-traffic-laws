CREATE TABLE accounts (
 id UUID PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE, password VARCHAR(100) NOT NULL,
 name VARCHAR(100) NOT NULL, role VARCHAR(10) NOT NULL CHECK(role IN ('USER','ADMIN')),
 enabled BOOLEAN NOT NULL DEFAULT TRUE, token_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE content (
 id UUID PRIMARY KEY, kind VARCHAR(20) NOT NULL CHECK(kind IN ('questions','signs','documents')),
 external_id VARCHAR(250) NOT NULL, data TEXT NOT NULL, published BOOLEAN NOT NULL DEFAULT FALSE,
 version BIGINT NOT NULL DEFAULT 0, UNIQUE(kind, external_id)
);
CREATE TABLE exams (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES accounts(id), started_at TIMESTAMP WITH TIME ZONE NOT NULL,
 expires_at TIMESTAMP WITH TIME ZONE NOT NULL, submitted_at TIMESTAMP WITH TIME ZONE,
 snapshot TEXT NOT NULL, answers TEXT NOT NULL, score INTEGER, critical_failed BOOLEAN, passed BOOLEAN
);
CREATE INDEX exams_owner ON exams(owner_id, started_at);
CREATE TABLE study_attempts (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES accounts(id), question_id UUID NOT NULL REFERENCES content(id),
 chapter INTEGER NOT NULL, correct BOOLEAN NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX study_owner ON study_attempts(owner_id, chapter);
CREATE TABLE chat_messages (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES accounts(id), question TEXT NOT NULL,
 answer TEXT, citations TEXT NOT NULL, state VARCHAR(20) NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX chat_owner ON chat_messages(owner_id, created_at);
