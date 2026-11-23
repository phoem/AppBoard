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

### Local library and generation diagnostics · implemented

Save the prompt and draft when generation starts. Save accepted main pages, features and edits to SQLite. Verify that an unfinished app can retry after reopening, that an imported copy is independent, and that edits survive a failed save or concurrent writer. Exercise the desktop library search and reopen completed features with zero additional model requests. [ADR 0006](adr/0006-local-app-library.md)

Live testing with LM Studio exposed native pages that used a browser canvas API, repeated the calling page, or failed only on click. Stream the generated title early, send a feature-specific request, and check drawing and pointer handling before installation. Time first title and interactive completion separately because inference latency varies across requests.

### Progressive rendering and lazy feature generation · implemented

The first-paint regression test holds back all model bytes for both the main page and first feature and inspects actual window pixels. It then delivers an unfinished drawing section and verifies the model's pixels while the response is still paused. Measure local first paint, first model-drawn content and time to usable controls separately.

Two Windows runs with LM Studio and `google/gemma-4-e4b` used the same field-notebook prompt and clicked Gallery. The observed local layout appeared in 0.39–0.47 s for the first panel and 0.02–0.03 s for Gallery. The first model drawing arrived in 1.61–1.94 s and 0.88 s, respectively. The home page was usable in 2.43–2.76 s. Gallery took 1.68 s on its first attempt in one run and 12.25 s with an automatic correction in the other. These are sample timings from a running local server.

### Feature first-pass verification

The server trace for the 12.25 s visit shows a cancelled first response and a 10.67 s replacement. Its logged request truncates the validation error. In a separate six-trial replay of `View Gallery` on the same model, four first attempts put a description in the color argument of an extra navigation button.

In the final run, six fresh empty Galleries became usable on the first request in 1.07–1.49 s. A populated Gallery showed both supplied entries on its first request in 0.98 s. A custom counter used the full drawing format, opened on its first request in 3.64 s and incremented on click. Timings run from feature navigation to the validated page becoming interactive on a running LM Studio model. Regression tests cover scrolling, embedded thumbnails, saved source and loops spanning streamed fragments.

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
