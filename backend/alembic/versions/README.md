# Migration revisions

Alembic-generated revision files live in this directory. Every generated migration must
be reviewed before it is committed.

Current chain:

- `0001`: v0.1 relational and pgvector schema.
- `0002`: parsed-document checksum, parser version, quality, and timestamp.
- `0003`: source PDF checksum, byte size, and download timestamp.
- `0004`: durable job dispatch lease timestamp and recovery index.

Never edit a revision after it has been applied outside a disposable local database. Add a new reversible migration and run `alembic check` after changing SQLAlchemy metadata.
