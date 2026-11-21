# Multi-Agent Development Protocol

This repository uses a shared-workspace orchestration model. All agents may see the same working tree, so coordination is based on explicit ownership, resource policy, and append-only handoffs rather than isolated branches.

The root orchestrator owns scheduling, integration, recovery, and coordination of every Git mutation. Workers own bounded implementation tasks and must not use Git or edit outside their grants.

## Authority and instruction scope

- This file is the repository-wide default. A more deeply nested `AGENTS.md` may add stricter, path-specific rules.
- The orchestrator resolves conflicts between instructions, records durable decisions, and may pause work when repository safety is unclear.
- Workers must stop and report any conflict between their assignment, the resource registry, a nested instruction file, or observed workspace state.
- `.agent-state/README.md` defines the state-file formats and persistence boundary.

## Roles

### Orchestrator

Among agents, the orchestrator is the only role allowed to:

- create or revise task decomposition and dependency ordering;
- assign worker IDs and names;
- grant, change, or revoke write access and locks;
- edit orchestrator-only resources;
- approve changes to frozen contracts;
- resolve overlapping work and integrate worker results;
- run `git add`, `git commit`, `git merge`, `git rebase`, `git restore`, `git checkout`, `git reset`, or other commands that change Git state;
- promote runtime discoveries into durable repository knowledge; and
- perform recovery after an interrupted or failed worker.

The orchestrator may delegate investigation, implementation, tests, or review, but retains responsibility for the final tree.

### Workers

Workers:

- operate only within an explicit task and write grant;
- never run commands that mutate Git state;
- treat ungranted files as read-only;
- inspect current policy and locks before editing;
- keep their runtime record current;
- checkpoint material progress; and
- submit an integration request rather than committing or merging.

A worker may read broadly unless a resource is classified `read-only` for a narrower reason, contains secrets, or another instruction restricts access.

## Git operating mode

At the beginning of every coordinated run, before dispatching workers or making any Git mutation, the orchestrator must ask the user to choose a Git operating mode. If the user already selected a mode in the current request, confirm and use it without asking again. Until a mode is selected, the orchestrator may inspect Git state but must not stage or commit.

Offer these choices in plain language:

1. **Orchestrator-managed:** The orchestrator stages and commits each accepted integration unit without requesting separate approval for every commit.
2. **Approval-gated:** At each proposed commit boundary, the orchestrator presents the changes, status, verification results, proposed commit message, and exact `git add` and `git commit` commands. It then pauses and asks whether the user wants the orchestrator to run those commands or will run them personally.
3. **User-managed:** The orchestrator never stages or commits. At each proposed commit boundary, it presents the same review packet and exact commands, then waits for the user to run them and confirm when work may continue.

Record the selected mode near the beginning of `runtime/orchestrator.log`. A mode applies only to the current coordinated run unless the user explicitly says otherwise. The user may change modes at any time; record the change before continuing.

The Git operating mode changes who authorizes or performs commits, not ownership: workers never stage, commit, amend, merge, rebase, reset, restore, or otherwise mutate Git state in any mode.

### Commit boundaries

For a large plan, use segmented commits at coherent integration boundaries. Do not default to one final bulk commit. A good commit is independently understandable, contains accepted work for one outcome or dependency boundary, and leaves the repository valid and buildable whenever practical.

Typical boundaries include:

- an agreed contract or schema change and its focused verification;
- one independently useful backend or frontend capability;
- a migration paired with the code needed to support it;
- tests or documentation that complete an already integrated behavior; or
- a focused integration repair.

Do not create a commit merely because a timer elapsed, a worker emitted a checkpoint, or one file changed. A worker checkpoint is temporary recovery state; it is not a Git commit boundary. Conversely, do not combine unrelated accepted units solely to reduce the number of commits.

Before every commit, the orchestrator reviews the actual diff, confirms provenance and scope, runs proportionate verification, and excludes unrelated user or worker changes. Stage explicit paths rather than using broad commands such as `git add .` when the workspace contains or may contain unrelated changes.

In orchestrator-managed mode, report the resulting commit hash and summary after each commit. In approval-gated or user-managed mode, the pre-commit review packet must include:

- the integration unit and why it is ready;
- changed paths and a concise diff summary;
- tests or checks run, including failures or checks not run;
- known risks, dependencies, and unrelated working-tree changes left unstaged;
- the proposed commit message; and
- exact path-scoped `git add` command(s) and the exact `git commit` command.

After presenting that packet, pause. In approval-gated mode, continue only after the user authorizes the orchestrator to commit or confirms they committed it themselves. In user-managed mode, continue only after the user confirms the commit is complete or explicitly instructs the orchestrator to proceed without it. Before resuming, inspect Git state to confirm the expected result and account for any user adjustments.

## Worker identity

Every worker receives an immutable ID and a short descriptive name at creation.

- ID format: `w-<three digits>`, for example `w-003`.
- Name format: lowercase kebab case describing responsibility, for example `auth-tests`.
- Display form: `w-003/auth-tests`.
- IDs are never reused during the same orchestration run, even after failure or cancellation.

The orchestrator is identified as `orchestrator`. Each worker records its assignment in `.agent-state/runtime/workers/<id>/worker.json` before making changes.

## Resource registry and classifications

`.agent-state/resource-registry.json` is the durable source of repository resource policy. Rules use repository-relative paths or glob patterns. More specific rules override broader rules. A nested `AGENTS.md` may impose additional restrictions but may not silently weaken a durable rule.

Every writable resource must resolve to one classification:

| Classification | Meaning | Edit rule |
| --- | --- | --- |
| `worker-exclusive` | A component can be owned by one worker at a time. | One worker holds an exclusive lock for the granted scope. |
| `serialized-shared` | Multiple tasks may need the resource, but edits must be sequenced. | One writer at a time; orchestrator schedules a queue and verifies between writers. |
| `orchestrator-only` | Central integration or high-contention resource. | Only the orchestrator edits it. Workers propose changes in integration requests. |
| `frozen-contract` | Public interface, schema, protocol, or compatibility boundary. | Read by default; modification requires explicit orchestrator approval and contract review. |
| `read-only` | Reference, vendored, security-sensitive, or intentionally immutable content. | No agent edits it unless the orchestrator first changes the durable policy. |
| `generated` | Output owned by a generator or build process. | Do not hand-edit; edit the source and let the orchestrator run or approve regeneration. |
| `unclassified` | Policy has not yet been decided. | Read-only until the orchestrator classifies and records it. |

Do not interpret a missing registry entry as permission to write. New files inherit the most specific matching parent or glob rule. If none exists, they are `unclassified`.

Durable classifications describe normal policy across runs. Runtime locks describe who may write now. Both must permit an edit.

## Dynamic locks

Current locks live in `.agent-state/runtime/locks.json` and are controlled by the orchestrator.

Each lock records:

- a unique lock ID;
- resource path or glob;
- mode (`exclusive`, `serialized`, `orchestrator-exclusive`, or `frozen`);
- holder or queue;
- reason and associated task;
- acquisition and optional expiry timestamps; and
- status (`active`, `released`, or `revoked`).

Lock rules:

1. The orchestrator checks path overlap, including parent directories and globs, before granting a lock.
2. Workers may not create, transfer, broaden, or release their own locks. They request changes from the orchestrator.
3. An exclusive grant covers only the named paths. It does not imply permission to update manifests, snapshots, lockfiles, generated output, or shared registries.
4. A worker encountering a needed out-of-scope edit stops that portion of work and submits a scope-change or orchestrator-edit request.
5. The orchestrator releases locks after integration, cancellation, or recovery—not merely when a worker says implementation is done.
6. Stale or expired locks are not automatically safe to take. The orchestrator first inspects the worker record, change history, and checkpoint.

When two resources overlap, the stricter policy wins. `read-only` and `frozen-contract` restrictions take precedence over ordinary write locks.

## Planning and dependency-aware scheduling

Before dispatching workers, the orchestrator:

1. confirms the Git operating mode;
2. identifies deliverables and verification criteria;
3. maps required resources to classifications;
4. records any new durable resource decisions;
5. builds a dependency graph of tasks, contract changes, and likely commit boundaries;
6. separates independent work from serialized or integration work;
7. grants the narrowest useful locks; and
8. starts only tasks whose prerequisites are satisfied.

Tasks should declare:

- `task_id`, outcome, and acceptance criteria;
- worker ID/name;
- dependencies and blockers;
- read scope and write scope;
- lock IDs;
- expected tests or inspection;
- prohibited or orchestrator-owned resources; and
- handoff expectations.

Parallelism is appropriate only when write sets do not overlap and neither task depends on the other's unintegrated output. Contract-first work must be resolved before downstream implementation. Changes to serialized-shared resources are queued in dependency order, not arrival order.

## Worker lifecycle

### 1. Assigned

The orchestrator creates the worker identity, task record, dependencies, write grant, and locks. The worker verifies that the assignment is internally consistent.

### 2. Active

The worker reads relevant instructions and source, then implements within scope. It records meaningful events in `changes.jsonl` and concise human-readable progress in `work.log`.

### 3. Checkpointed

After a coherent unit of progress, and before risky or broad edits, the worker refreshes `checkpoint.patch`. A checkpoint is a recovery aid, not permission to overwrite concurrent work.

### 4. Ready for integration

The worker stops editing, runs authorized verification, summarizes outcomes, and appends an integration request. Its locks remain held until the orchestrator finishes review.

### 5. Integrated, returned, failed, or cancelled

The orchestrator reviews provenance and the actual diff. It may integrate the work, return it with specific corrections, recover partial work, or discard it. The orchestrator updates status and releases or reassigns locks.

Workers must not continue editing after entering `ready-for-integration` unless the orchestrator returns the task and renews its grant.

When an accepted integration unit reaches its planned commit boundary, the orchestrator follows the selected Git operating mode before scheduling work that requires that committed boundary. Independent work that does not depend on the pending commit may continue only when its locks and write set remain non-overlapping.

## Runtime records

Runtime data is local and disposable as a transport layer, but it must be accurate during a run.

### `worker.json`

Current structured state for one worker. At minimum it contains identity, task, status, dependencies, granted paths, lock IDs, timestamps, and latest checkpoint information. Valid statuses are:

`assigned`, `active`, `blocked`, `ready-for-integration`, `returned`, `integrated`, `failed`, and `cancelled`.

### `work.log`

Human-readable activity for diagnosis. Keep entries short, timestamped, and free of secrets. This is not the authoritative mutation record.

### `changes.jsonl`

Append-only provenance events. Record observed, created, modified, deleted, generated, tested, checkpointed, and blocked events. Each line must be an independent JSON object with timestamp, worker ID, task ID, event type, paths, and a concise reason or result.

### `checkpoint.patch`

An exact diff of recoverable worker changes. Refresh it at meaningful boundaries. Never treat a patch as authoritative without comparing it to the shared working tree.

### Global runtime files

- `locks.json`: current lock snapshot.
- `integration-queue.jsonl`: append-only integration and scope-change requests.
- `orchestrator.log`: human-readable scheduling, review, and recovery activity.

Runtime files must never contain credentials, tokens, private keys, or unnecessary personal data.

## Integration requests

A worker submits one JSON object per request to `.agent-state/runtime/integration-queue.jsonl`. Request types include `integrate`, `scope-change`, `orchestrator-edit`, `contract-change`, and `unblock`.

An `integrate` request should contain:

```json
{"request_id":"ir-20260822-004","type":"integrate","timestamp":"2026-08-22T18:30:00Z","worker_id":"w-003","task_id":"task-auth-tests","status":"pending","summary":"Add expired-token coverage","paths":["tests/auth/token.test.ts"],"checks":[{"command":"npm test -- token.test.ts","result":"passed"}],"checkpoint":"runtime/workers/w-003/checkpoint.patch","dependencies":[],"risks":[],"orchestrator_actions":[]}
```

Workers report commands and outcomes honestly; they do not claim checks they did not run. If the work requires an orchestrator-owned file, list the exact proposed edit under `orchestrator_actions` instead of making it.

The orchestrator processes requests only when their dependencies are integrated and required locks are still valid. Review includes scope, policy, diff, tests, generated artifacts, contract impact, and interference from other workers.

## Checkpoints and provenance

Use checkpoints to preserve recoverable progress during long tasks, risky transformations, and handoffs. Prefer small coherent checkpoints over one final bulk snapshot.

Provenance must answer:

- who changed or proposed each path;
- under which task and lock;
- why it changed;
- which source or contract informed it;
- what verification ran and with what result; and
- whether the orchestrator modified it during integration.

The orchestrator records its own integration edits in `orchestrator.log` and, when material to future work, in durable repository decisions. Runtime provenance supplements the actual diff; it never replaces inspection of the tree.

## Recovery

When a worker is interrupted, stale, or failed, the orchestrator:

1. freezes the affected scope and prevents reassignment;
2. reads `worker.json`, `changes.jsonl`, `work.log`, and `checkpoint.patch`;
3. compares recorded paths and the checkpoint with the current working tree;
4. identifies changes belonging to other workers or the user;
5. decides to resume, integrate a safe subset, reassign, or abandon the work;
6. records the decision and any preserved provenance;
7. updates worker and lock status; and
8. only then grants the scope to another worker.

Never use a broad reset, checkout, clean, or blind patch application for recovery. Existing workspace changes may belong to the user or another task. Recovery must be path-aware and reversible wherever possible.

## Contracts and frozen boundaries

`.agent-state/contracts.json` inventories important interfaces, schemas, protocols, and compatibility promises. A worker needing a contract change submits a `contract-change` request that includes rationale, consumers, migration impact, compatibility plan, and proposed verification.

The orchestrator reviews downstream dependencies before approving. Approval is explicit and scoped; it does not unfreeze unrelated contracts. Accepted changes update implementation, consumers, tests, and the durable contract entry together.

## Knowledge promotion

Runtime observations are not automatically durable truth. At integration or run close, the orchestrator promotes only knowledge that is stable, repository-specific, and useful to future agents.

Promote:

- recurring resource ownership or contention rules to `resource-registry.json`;
- durable interfaces and compatibility boundaries to `contracts.json`;
- architectural choices, rejected alternatives, operational constraints, and recovery lessons to `repository-decisions.md`; and
- protocol clarifications to `.agent-state/README.md` or the applicable `AGENTS.md`.

Do not promote transient worker status, timestamps, speculative conclusions, raw logs, or one-off failures. Durable entries should cite repository paths or evidence, explain rationale, and include a review trigger when the decision may become stale.

## End-of-run checklist

Before declaring the coordinated run complete, the orchestrator verifies that:

- all worker statuses are terminal;
- all integration requests are resolved or explicitly deferred;
- runtime locks are released or explained;
- accepted changes and tests have been reviewed;
- generated files came from their declared sources;
- contract and resource registries reflect accepted durable changes;
- useful knowledge has been promoted without copying runtime noise;
- Git changes contain no `.agent-state/runtime/` content; and
- accepted work is divided into coherent commits, or any intentionally uncommitted work is clearly identified;
- every orchestrator-created commit hash and every user-managed pending command is reported;
- the final handoff identifies remaining risks and unverified checks.

## AppBoard working agreements

Use the manage-shared-workspace-orchestration skill for development unless Jordan specifies otherwise. Keep temporary files and build chunks out of the project tree. Maintain tests, the implementation plan and architecture decision records alongside changes.
