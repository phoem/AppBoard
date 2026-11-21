# AppBoard implementation plan

## First build

1. Open a resizable 1920 × 1080 Qt Quick window with an empty board. Provide New and Open as board-level commands.
2. Give each app its own movable, resizable panel and isolated document. Support standard HTML controls, JavaScript, CSS, SVG, Canvas and WebGL where the device supports it.
3. Make source the saved artifact. Edit manually or generate from a prompt, apply an edit, save atomically, close and reopen the same project.
4. Connect a configurable chat-completions model endpoint. Keep inference off the UI thread and keep the previous draft when generation fails.
5. Expose a narrow optional browsing capability with a real Chromium view and navigation events. Preserve the browsing instance across toolbar source edits.
6. Verify package compatibility, model response handling, runtime isolation settings and end-to-end desktop behavior. Record the decisions in ADRs.

## Following milestones

| Milestone | Acceptance test |
| --- | --- |
| Configurable layout and multiple browser surfaces | Generate vertical tabs or a split browser. Move the toolbar while retaining page history and entered form data. |
| Durable app-owned state | Offer per-project storage with explicit export, deletion and size limits. A generated scorekeeper can resume a match after restart. |
| Visual editing and history | Change a selected element's style, revise it by prompt, undo both edits and reopen the resulting source. |
| Distribution and hardware validation | Package a signed desktop build. Verify DPI, multi-monitor placement, WebGL and frame timing on representative GPUs. |

Each new capability needs a documented interface, an integration test using an unfamiliar app, and an ADR when it changes the runtime or persistence boundary.
