# OmniCare Evaluation V2

## Gates

- Unit and deterministic integration tests: 100%.
- Holdout pass rate: at least 92%.
- No foreign-order leakage, forbidden tool call, unsafe write, mandatory-handoff miss, or internal-content leakage.
- Citation cases must resolve the expected active document/version.
- Multi-turn cases must preserve the selected customer and order context.

## Commands

```powershell
pnpm test
pnpm eval:audit
py -3.13 -m app.evaluation_v2_runner --dataset ../../datasets/evaluation-v2.sample.json --base-url http://localhost:8000 --output ../../datasets/artifacts/evaluation-v2-report.json
pnpm --dir apps/web kb:test-lifecycle
```

Run the Python evaluation command from `apps/ai-service`.

## Dataset rules

- Keep every semantic cluster inside one split.
- Never import evaluation datasets from production modules.
- Do not copy holdout questions into prompts, routing tables, retrieval aliases, or KB fixtures.
- Declare required, allowed, and forbidden tools separately.
- Define expected UI, model profile, active entity, citation terms, and handoff behavior where applicable.
- Treat synthetic paraphrases as variants of one scenario, not independent coverage.

## Reports

- `datasets/artifacts/evaluation-audit.json`: duplicates and effective case count.
- `datasets/artifacts/evaluation-v2-report.json`: trajectory results and release gate.
- `datasets/artifacts/kb-lifecycle-report.json`: add, archive, restore, retrieval rank, answer grounding, and cleanup.
