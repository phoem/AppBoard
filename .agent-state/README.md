# Agent State

This directory separates durable repository coordination knowledge from ephemeral multi-agent runtime state.

## Persistence boundary

The following files are durable and belong in version control:

- `README.md` — protocol, schemas, and format guidance.
- `resource-registry.json` — current structured resource classifications and ownership policy.
- `contracts.json` — current structured contract and compatibility-boundary registry.
- `repository-decisions.md` — human-readable rationale and durable coordination decisions.

Everything under `runtime/` is local execution state and is ignored by Git. It may be deleted after a run is closed and useful knowledge has been promoted.

## Format convention

| Format | Use |
| --- | --- |
| JSON | Current structured state read and updated as a whole. |
| JSONL | Append-only event or request history; one complete JSON object per line. |
| Markdown | Protocol, rationale, decisions, and human/agent guidance. |
| `.patch` | Exact recoverable diffs. |
| `.log` | Concise human-readable runtime activity. |

Do not use JSONL as a mutable snapshot and do not use logs as machine-authoritative state.

## Directory layout

```text
.agent-state/
├── README.md
├── resource-registry.json
├── contracts.json
├── repository-decisions.md
└── runtime/                         # ignored
    ├── locks.json                   # current lock snapshot
    ├── integration-queue.jsonl      # append-only requests/events
    ├── orchestrator.log             # readable orchestrator activity
    └── workers/
        └── <worker-id>/
            ├── worker.json          # current worker/task state
            ├── work.log             # readable worker activity
            ├── changes.jsonl         # append-only provenance
            └── checkpoint.patch      # recoverable exact diff
```

The orchestrator creates worker directories as workers are dispatched. Runtime files should use UTF-8, repository-relative paths with `/` separators, ISO 8601 UTC timestamps, and stable IDs.

At run start, the orchestrator records the user-selected Git operating mode in `orchestrator.log`: `orchestrator-managed`, `approval-gated`, or `user-managed`. This is runtime preference, not durable repository policy. See the root `AGENTS.md` for commit boundaries and the required review packet.

## Runtime templates

Initial `runtime/locks.json`:

```json
{
  "schema_version": 1,
  "updated_at": null,
  "locks": []
}
```

Example `worker.json`:

```json
{
  "schema_version": 1,
  "worker_id": "w-003",
  "name": "auth-tests",
  "task_id": "task-auth-tests",
  "status": "assigned",
  "objective": "Add expired-token coverage",
  "dependencies": [],
  "read_scope": ["src/auth/**", "tests/auth/**"],
  "write_scope": ["tests/auth/token.test.ts"],
  "lock_ids": ["lock-007"],
  "prohibited_paths": ["package.json"],
  "acceptance_criteria": ["Expired tokens are rejected by a focused test"],
  "verification": ["npm test -- token.test.ts"],
  "created_at": "2026-08-22T18:00:00Z",
  "updated_at": "2026-08-22T18:00:00Z",
  "checkpoint": null,
  "blocked_on": []
}
```

Example lock entry inside `locks.json`:

```json
{
  "lock_id": "lock-007",
  "resource": "tests/auth/token.test.ts",
  "classification": "worker-exclusive",
  "mode": "exclusive",
  "holder": "w-003",
  "queue": [],
  "task_id": "task-auth-tests",
  "reason": "Focused test implementation",
  "acquired_at": "2026-08-22T18:00:00Z",
  "expires_at": null,
  "status": "active"
}
```

Example `changes.jsonl` lines:

```jsonl
{"timestamp":"2026-08-22T18:05:00Z","worker_id":"w-003","task_id":"task-auth-tests","event":"observed","paths":["src/auth/token.ts"],"reason":"Read token expiry behavior before writing tests"}
{"timestamp":"2026-08-22T18:20:00Z","worker_id":"w-003","task_id":"task-auth-tests","event":"modified","paths":["tests/auth/token.test.ts"],"reason":"Add expired-token rejection case"}
{"timestamp":"2026-08-22T18:25:00Z","worker_id":"w-003","task_id":"task-auth-tests","event":"tested","paths":["tests/auth/token.test.ts"],"result":"passed","command":"npm test -- token.test.ts"}
```

Example integration request in `integration-queue.jsonl`:

```jsonl
{"request_id":"ir-20260822-004","type":"integrate","timestamp":"2026-08-22T18:30:00Z","worker_id":"w-003","task_id":"task-auth-tests","status":"pending","summary":"Add expired-token coverage","paths":["tests/auth/token.test.ts"],"checks":[{"command":"npm test -- token.test.ts","result":"passed"}],"checkpoint":"runtime/workers/w-003/checkpoint.patch","dependencies":[],"risks":[],"orchestrator_actions":[]}
```

## Durable-file maintenance

- Keep registry changes small, reviewable, and valid JSON.
- Prefer repository-relative paths and explicit glob syntax.
- Add rationale to each policy or contract entry; use `repository-decisions.md` when reasoning is too substantial for a short field.
- Set uncertain facts to `unknown` or leave optional fields empty; do not invent metadata.
- At run close, promote stable findings, resolve integration requests, release locks, and verify that runtime content is absent from Git changes.

The authoritative behavioral rules are in the root `AGENTS.md` and any more-specific nested `AGENTS.md` files.
