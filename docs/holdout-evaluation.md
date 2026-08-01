# Anti-overfit Holdout Evaluation

## Method

- Runtime seed hash: `08f89b65bfdd`.
- `300` unique questions generated from `100` support scenarios with three deterministic language mutations.
- Production code cannot load evaluation datasets or reference evaluation case ID prefixes.
- Deterministic checks cover intent, tools, UI, forbidden content, citation presence and citation-title relevance.
- An independent LLM judge scores relevance, factuality, naturalness and completeness.
- Judge failures remain failures; reruns do not convert a failure into a pass.

## Result — 2026-07-30

### Full hybrid baseline

- Passed: `212/300`.
- Pass rate: `70.67%`.
- TTFT P50: `8 ms`.
- TTFT P95: `1,879 ms`.
- Most frequent failures: completeness `81`, factuality `17`, relevance `13`, latency `3`.

### Deterministic structural gate

- Passed: `296/300`.
- Pass rate: `98.67%`.
- Verifies routing, required tools, permissions, UI actions, citations and stream contract.
- This score is not used as the conversational quality score.

### Failure-subset regression

- Re-ran the `88` failed hybrid cases after supervisor, transaction-answer and retrieval-diversity changes.
- Passed: `41/88`; previous result on the same subset: `0/88` by definition.
- Remaining quality failures: `36`; latency-only failures: `11` under concurrent external-provider load.
- Cancellation subset passed `14/16`; one failure was an inconsistent judge assessment of a verified tool result, one was a latency spike.

### Harness quality upgrade — final run

- Full hybrid: `269/300`, pass rate `89.67%`.
- Full structural: `299/300`, pass rate `99.67%`.
- Unit tests: `35/35`.
- TTFT is emitted at pipeline acceptance through an invisible empty token; user-visible answer tokens remain streamed normally.
- Added deterministic response quality metadata, verified transaction facts and automatic `KnowledgeGap` recording.
- Retrieval now decomposes multi-part questions, expands customer language to canonical Shopee terms, prevents score saturation and excludes TikTok Shop documents from Shopee answers.
- The strict `90%` hybrid release gate is not yet met; the result is short by one passing case.

### Ontology canary — 2026-07-30

- Removed phrase-level `QUERY_ALIASES` from production retrieval.
- Added ontology-based `QueryPlan` with concepts, propositions and required evidence types.
- Added AST/similarity tests preventing routing and retrieval literals from copying holdout questions.
- Canary seed hash: `11455e4855de`; generated only after the ontology implementation was frozen.
- Canary structural: `300/300`, pass rate `100%`.
- Canary hybrid: `282/300`, pass rate `94%`.
- Remaining canary failures: completeness `17`, factuality `4`, relevance `2`.
- The canary passes the strict hybrid release gate without question-level aliases or evaluation dataset access from production.

The previous marketplace score of `200/200` measured repeated regression prompts and citation presence. It must not be presented as general chatbot accuracy.

Compact release metrics live in `datasets/artifacts/release-manifest.json`; raw batch reports are reproducible outputs and are not retained.

## Priority fixes

1. Fill verified KB gaps for technical troubleshooting, shipping actions, payment failures and privacy summaries.
2. Add offline judge calibration cases so tool-verified facts are scored consistently.
3. Run the full hybrid gate after provider latency stabilizes; target remains at least `90%`.
4. Keep broad-policy retrieval diverse across sections while preserving authority and effective-date filters.
