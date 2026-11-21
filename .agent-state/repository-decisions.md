# Repository Coordination Decisions

This log preserves stable, repository-specific orchestration knowledge. It is not a runtime activity log. Add entries only when a decision will help future agents plan, classify resources, integrate work, or recover safely.

## Entry template

### `decision-YYYYMMDD-short-name` — Title

- **Status:** accepted | superseded | deprecated
- **Date:** YYYY-MM-DD
- **Scope:** repository-relative paths or subsystem
- **Decision:** The durable rule or conclusion.
- **Rationale:** Evidence, constraints, and rejected alternatives that explain why.
- **Consequences:** Scheduling, ownership, contract, testing, or recovery effects.
- **Evidence:** Relevant repository paths, tests, issues, or prior decision IDs.
- **Review trigger:** The condition that should cause reevaluation.
- **Supersedes / superseded by:** Decision ID or `none`.

## Accepted decisions

### `decision-20260822-state-persistence` — Separate durable coordination knowledge from runtime state

- **Status:** accepted
- **Date:** 2026-08-22
- **Scope:** `.agent-state/**`, `.gitignore`, and root orchestration policy
- **Decision:** Version `README.md`, `resource-registry.json`, `contracts.json`, and `repository-decisions.md`. Ignore only `.agent-state/runtime/`.
- **Rationale:** Resource policy, contract knowledge, and architectural reasoning remain useful across runs and should evolve with the repository. Locks, worker status, logs, queues, and checkpoints are volatile execution artifacts that create churn and stale ownership if committed.
- **Consequences:** The orchestrator must promote useful knowledge before runtime cleanup. Runtime state cannot be assumed to exist after checkout.
- **Evidence:** `.agent-state/README.md`, `.agent-state/resource-registry.json`, and `.gitignore`.
- **Review trigger:** A future coordination mechanism requires a new category of durable state or a runtime artifact becomes necessary for reproducibility.
- **Supersedes / superseded by:** none

### `decision-20260822-mixed-state-formats` — Use formats according to state semantics

- **Status:** accepted
- **Date:** 2026-08-22
- **Scope:** `.agent-state/**`
- **Decision:** Use JSON for current structured state, JSONL for append-only history, Markdown for protocol and rationale, `.patch` for exact diffs, and `.log` for human-readable runtime activity.
- **Rationale:** A single format obscures whether a file is a snapshot, event stream, explanation, or recovery artifact. Semantic formats make correct updates and review more predictable.
- **Consequences:** JSONL records are appended rather than rewritten; logs are not authoritative; patches must be compared with the current tree before application.
- **Evidence:** `.agent-state/README.md`.
- **Review trigger:** Tooling or scale makes a format unsuitable while preserving the same semantic distinction.
- **Supersedes / superseded by:** none

### `decision-20260822-segmented-git-control` — Select Git control per run and commit coherent integration units

- **Status:** accepted
- **Date:** 2026-08-22
- **Scope:** coordinated runs, integration boundaries, and Git history
- **Decision:** At run start, the user selects orchestrator-managed, approval-gated, or user-managed Git operation. Large plans are committed in coherent, independently reviewable integration units rather than one default bulk commit. Worker checkpoints remain recovery artifacts and do not themselves trigger commits.
- **Rationale:** Segmented commits provide useful rollback and review points, while an explicit operating mode lets the user choose between autonomy and direct commit control without allowing workers to mutate Git state.
- **Consequences:** Approval-gated and user-managed runs pause at proposed commit boundaries and provide status, verification, risks, commit message, and exact path-scoped commands. Orchestrator-managed runs report each resulting commit. Dependent work waits when it requires a pending commit boundary.
- **Evidence:** Root `AGENTS.md`, section “Git operating mode.”
- **Review trigger:** The repository adopts a different integration model or needs a stricter commit-signing, review, or release policy.
- **Supersedes / superseded by:** none
