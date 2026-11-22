# ADR 0006 · Local app library and portable copies

Accepted 2026-11-22

## Context

A panel used to be the only copy of a generated app until its owner chose a filename. Reopening a feature without regenerating it depended on saving the file after visiting that feature. AppBoard needs to retain accepted work automatically and offer a way to find and share it.

## Decision

Store apps in SQLite under Qt’s per-user local application data directory. The library uses a stable random ID per app, a revision counter, searchable name and brief, last-saved timestamp, pending flag and the complete versioned project payload. SQLite’s schema version is independent of the portable project version.

Create a record when a user starts generation, runs a hand-authored app or imports a file. Store the initial prompt and draft even if inference is interrupted. On reopening an unfinished main page, Retry uses the current local model settings. Save the whole project in a transaction after each accepted generation or applied edit. Interim previews stay in memory. A failed revision or feature leaves the previous stored source usable.

Use a revision check on update. If another process has edited the same record, preserve the current session’s edits as a new library copy and notify the user. A failed write leaves the panel open with a retry action and a close prompt for unsaved changes.

A portable export contains the existing versioned project. Import assigns it a new library identity. Users can share individual apps without transferring the database or linking changes back to the sender. Sharing works between separate installations using the file exchange.

## Consequences

Completed pages reopen without contacting a model server. Starting AppBoard still opens a blank board. Browsing state and app-owned runtime variables remain session-scoped. Cross-device synchronization and a shared online catalog would require a separate service and access model.

See `appboard/library.py`, `tests/test_library.py` and `tests/test_desktop.py` for the storage contract and compatibility checks.
