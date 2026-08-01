# Architecture

```mermaid
flowchart LR
  W[Web Chat / Help Center] --> N[Channel normalizer]
  N --> A[FastAPI agent]
  A --> R[Knowledge retrieval]
  A --> T[Transaction tools]
  A --> H[Reply or human handoff]
  R --> P[(PostgreSQL + pgvector)]
  T --> P
```

## Agent graph

```mermaid
flowchart TD
  S[Normalize] --> G[Safety guard]
  G --> C[Classify and extract]
  C --> T[Verified transaction tools]
  T --> R[Effective public knowledge retrieval]
  R --> D{Evidence decision}
  D -->|Enough| A[Grounded answer]
  D -->|Missing| Q[Clarification]
  D -->|Risk or conflict| H[Human handoff]
```

Transaction tools enforce customer identity and order ownership in SQL. Knowledge retrieval filters visibility, publication state and effective dates before ranking.
