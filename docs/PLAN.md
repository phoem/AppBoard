# AppBoard implementation plan

## First build

1. Open a resizable 1920 × 1080 Qt Quick window with an empty board. Provide New and Open as board-level commands.
2. Give each app its own movable, resizable panel and isolated document. Support standard HTML controls, JavaScript, CSS, SVG, Canvas and WebGL where the device supports it.
3. Make source the saved artifact. Edit manually or generate from a prompt, apply an edit, save atomically, close and reopen the same project.
4. Connect a configurable chat-completions model endpoint. Keep inference off the UI thread and keep the previous draft when generation fails.
5. Expose a narrow optional browsing capability with a real Chromium view and navigation events. Preserve the browsing instance across toolbar source edits.
6. Verify package compatibility, model response handling, runtime isolation settings and end-to-end desktop behavior. Record the decisions in ADRs.

### First-build verification

Completed on Windows, 2026-11-21. The desktop tests exercise independent running apps, Canvas drawing, the model service contract, source editing, atomic save and reopen, and a real browser page that retains its form state during toolbar edits. An opt-in test also used LM Studio with the installed `google/gemma-4-e4b` model to generate a working tally button, click it in Chromium, and round-trip the generated project.

A graphics smoke check reported Direct3D 11 for the Qt Quick window and ANGLE on Intel UHD Graphics for the guest WebGL 2 context. This records the adapter selected on the development machine. Dedicated-GPU selection and cross-device performance measurements remain open.

## Following milestones

### Progressive rendering and lazy feature generation · implemented

Mount a panel when the user submits a prompt, paint complete drawing sections during streaming, then activate input on the validated page. Generate secondary pages on first navigation, retain the previous page on a cancelled request, and persist completed features with the app. The delayed-stream desktop test checks the first paint before releasing the remaining response, request counts before and after navigation, and reuse after reopening. See [ADR 0005](adr/0005-progressive-pages.md).

### Native 2D authoring and model discovery · implemented

New projects use version 2 drawing scripts. The runtime maps their primitives to native Qt Quick items. Version 1 documents keep their reader and renderer. Studio discovers provider-qualified model IDs and runs a valid generated native app as soon as the model completes its response. Coverage includes native pixels and input, save/reopen, resource limits, browser toolbar revisions, multi-provider routing and a live LM Studio generation test. See [ADR 0004](adr/0004-native-drawing.md).

| Milestone | Acceptance test |
| --- | --- |
| Configurable layout and multiple browser surfaces | Generate vertical tabs or a split browser. Move the toolbar while retaining page history and entered form data. |
| Durable app-owned state | Offer per-project storage with explicit export, deletion and size limits. A generated scorekeeper can resume a match after restart. |
| Visual editing and history | Change a selected element's style, revise it by prompt, undo both edits and reopen the resulting source. |
| Distribution and hardware validation | Package a signed desktop build. Verify DPI, multi-monitor placement, WebGL and frame timing on representative GPUs. |

Each new capability needs a documented interface, an integration test using an unfamiliar app, and an ADR when it changes the runtime or persistence boundary.
