# ADR 0002 · Editable project files

**Status** Accepted, 2026-11-21.

**Context** A user wants manual and prompted edits to the same design, and a saved app must reopen without contacting the model.

**Decision** Store version, title, editable HTML source and presentation options in one UTF-8 JSON file. Embed assets in the source for the first format. Validate on read and write. Write a temporary file beside the destination, flush it, then replace the original atomically. Detect external modifications before saving over a previously opened file.

**Consequences** A project can move between machines with its source intact. Each open instance has independent runtime state. Source edits restart the generated document. Separately hosted browsing content keeps its current page during a toolbar edit. The file-size limit bounds transport into the renderer.

**Review trigger** Introduce a migration strategy before adding binary assets, durable app data, or a second format version. Preserve version 1 reader fixtures.
