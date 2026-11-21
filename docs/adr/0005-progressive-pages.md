# ADR 0005 · Stream native pages and generate features on first use

**Accepted 2026-11-21.** Apps created from Studio use project version 3. The existing version 1 and version 2 formats keep their readers, editors and runtimes.

**Decision.** Request one page per chat completion. The model emits ordered drawing sections and a final input handler using a structured JSON response over server-sent events. The host recognizes complete JSON strings across transport boundaries. It renders each valid accumulated scene in a disposable, bounded drawing context. Only a validated complete page replaces committed source. The user sees the actual page accumulate while the model writes its interaction code.

**Feature navigation.** A pointer or keyboard action can request a named feature. The host generates an unseen page from the app brief, originating page source and shared state keys. Each page can use local app data. Back restores the previous drawing context. Completed feature source becomes part of the editable project and can run offline after saving. Provider settings belong to the local installation.

**Tradeoffs.** The first visit to a feature has inference latency. Streaming granularity depends on model output and provider buffering. A completed script that fails drawing validation gets one correction request. A stopped or failed request can be retried while the previous working page is available. Partial output is ephemeral. One runtime instance shares JSON state across its pages. Saving source and restoring live user data are separate capabilities.

**Review trigger.** Revisit the contract for concurrent generation within a single instance, durable user data, or additional shared native surfaces.
