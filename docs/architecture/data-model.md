# Data Model v0.1

Ruiyu is the DRI for the ER model, SQLAlchemy models, and Alembic migrations. Yifan reviews
fields used by summarization, embeddings, retrieval, recommendation, and evaluation before
the Milestone 1 schema freeze.

```mermaid
erDiagram
    users ||--|| user_preferences : has
    users ||--o{ user_events : emits
    users ||--o{ digests : receives
    papers ||--o{ paper_versions : has
    papers ||--o{ paper_authors : credits
    authors ||--o{ paper_authors : writes
    papers ||--o{ paper_chunks : contains
    papers ||--o{ paper_summaries : summarizes
    papers ||--o{ citations : cites
    papers ||--o{ digest_entries : appears_in
    digests ||--o{ digest_entries : contains
    users ||--o{ qa_conversations : owns
    qa_conversations ||--o{ qa_messages : contains
    pipeline_jobs }o--|| papers : processes

    users {
      uuid id PK
      string display_name
      timestamptz created_at
    }
    user_preferences {
      uuid user_id PK,FK
      jsonb explicit_topics
      jsonb followed_authors
      vector behavior_embedding
      int model_version
      timestamptz updated_at
    }
    user_events {
      uuid id PK
      uuid user_id FK
      uuid paper_id FK
      string event_type
      int duration_ms
      timestamptz occurred_at
      jsonb context
    }
    papers {
      uuid id PK
      string arxiv_id UK
      string title
      text abstract
      string primary_category
      string pdf_url
      string source_license
      string processing_status
    }
    paper_versions {
      uuid id PK
      uuid paper_id FK
      int version_number
      string source_checksum
      timestamptz submitted_at
    }
    authors {
      uuid id PK
      string normalized_name
      string semantic_scholar_id
    }
    paper_authors {
      uuid paper_id FK
      uuid author_id FK
      int author_order
    }
    paper_chunks {
      uuid id PK
      uuid paper_id FK
      string section_title
      int chunk_index
      int page_start
      int page_end
      text content
      vector embedding
      string embedding_model
      string content_hash
    }
    paper_summaries {
      uuid id PK
      uuid paper_id FK
      string status
      jsonb content
      string provider
      string model_snapshot
      string prompt_version
      string input_hash
      numeric estimated_cost
      timestamptz created_at
    }
    citations {
      uuid source_paper_id FK
      uuid target_paper_id FK
      string external_target_id
      float algorithm_weight
      jsonb algorithm_metadata
    }
    digests {
      uuid id PK
      uuid user_id FK
      string digest_type
      timestamptz generated_at
    }
    digest_entries {
      uuid digest_id FK
      uuid paper_id FK
      int rank
      float relevance_score
      string recommendation_reason
    }
    pipeline_jobs {
      uuid id PK
      uuid paper_id FK
      string stage
      string status
      int attempt_count
      text last_error
      string pipeline_version
      timestamptz started_at
      timestamptz finished_at
    }
```

## Fixed Decisions

- `papers` identifies a work; `paper_versions` records arXiv revisions.
- Authors are normalized relational entities, not an unqueryable JSON array.
- Digests are immutable generated snapshots so demos and evaluations are reproducible.
- Every event uses a client-generated UUID; duplicate IDs are ignored.
- Summaries are versioned by input hash, provider/model snapshot, and prompt version.
- Chunks retain section, page range, content hash, and embedding model metadata.
- A citation may initially reference an external paper ID; ingestion can resolve it later.
- Deleting a cached PDF does not delete metadata, chunks, or generated artifacts.

## Deferred Algorithm Decision

The exact behavior weights and decay formula are deliberately not frozen at Day 0. Ruiyu
must publish a versioned baseline before Milestone 3 begins. The initial implementation
will use deterministic event weights plus time-decayed weighted averaging of paper
embeddings; no online training is required for the MVP.
