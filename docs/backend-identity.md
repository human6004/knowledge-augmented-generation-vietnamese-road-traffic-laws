# Backend identity và physical database proof

`BackendIdentitySession` is one live preflight authority, shared by sample and
production. It resolves the complete pinned ProjectClient list, requires one
name/namespace match and one ID match, and independently looks up that ID.
Only explicit Neo4j URI and database in project `graph_store` are accepted.
Credentials remain in transport memory; no runtime default database is used.

The transport binds reads to that project URI. `DockerBackendTransport` checks
the running OpenSPG and Neo4j containers, host published ports, common network,
backend alias and DNS from inside OpenSPG. It reads the database catalog inside
the OpenSPG namespace with `Neo4jReadClient`, independently of the host verifier.
The default Docker adapter requires local Docker CLI/inspection/exec access and
supports the audited standalone HTTP/Bolt layout (8887/7474/7687). Missing access,
different ports, TLS or an unproved route fail closed. Such deployments must
supply a trusted in-process transport with equivalent live routing evidence;
JSON runner configuration cannot supply a proof or enable WRITE.

Catalog reads are parameterized `SHOW DATABASES` on `system`. A case variant is
accepted only when exactly one canonical catalog row resolves it. That row must
be ONLINE, with nonempty databaseID/serverID and a unique physical databaseID.
Backend and verifier must match canonical name, physical ID and serverID.
Runtime identity also binds Docker container/image/network identities.
These catalog fields are documented in the
[Neo4j database catalog](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/listing-databases/).
`database_identity()` retains its existing string API.

Only the exact immutable proof instance issued by an active session is accepted.
`validate()` re-reads project configuration, backend routing and both catalogs.
Copied, fabricated, mutated, stale or closed-session proof is refused before
dispatch. `lastStartTime` is not a freshness gate; the sample returns null.
Receipts explicitly serialize stable allowlisted identity only. They cannot
restore active authority. Resume creates a new session and re-proves live target;
no nonce/session token enters the run hash.

Production discovery still validates the scope/C3 input contract offline first. WriterConfig requires
the matching session/proof; constructor and shared `_invoke` guard enforce it for
native, inherited invoke/ainvoke, node and edge entry points. An existing writer
cannot swap its config, client or backend binding. Scope/vector/node barrier
checks remain required. GraphLock validates the same proof at construction and
acquisition; its filename remains SHA256(physical databaseID), so proven aliases
compete for one lock. Source-only locks do not use backend authority.

Production WRITE stays BLOCKED independently of a successful identity proof.
Production execution needs a fresh proof of the real project/runtime and separate
execution authority. No sample project/physical ID is a production default. Offline writer
intent capture proves pinned request serialization before HTTP; it is TEST
evidence, separate from LIVE backend identity evidence. See the current
[product architecture](architecture.md) and [runtime operations](runner.md).
