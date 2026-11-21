# ADR 0004 · Native 2D app rendering

**Accepted 2026-11-21.** Supersedes the default app runtime in ADR 0001. Existing version 1 documents retain their original renderer and public API.

**Decision.** New version 2 projects contain JavaScript logic and a `draw(g,w,h)` entry point. A separate QuickJS context per app runs with a memory, stack and execution-time budget. The host validates each frame and sends ordered primitives to native Qt Quick rectangles, text, paths and images. Qt manages device resources and composition. A browser app draws its controls with the same API and uses a separate Chromium surface for websites.

**Rationale.** The model can author and revise both interaction and drawing code without generating HTML, compiling native binaries, or loading arbitrary generated QML in the host. Explicit primitives also make generated frames inspectable in tests.

**Consequences.** Scripts own their state, hit testing and keyboard interactions. A finished model response can be validated and mounted immediately. Each source reload starts a fresh script context. Frame count, geometry and image limits are documented in the runtime reference. Review this decision when profiling shows a need for larger scenes, accessibility widgets, or direct GPU commands. [Qt Quick Shapes](https://doc.qt.io/qt-6/qml-qtquick-shapes-shape.html) · [QuickJS engine binding](https://pypi.org/project/quickjs-ng/)
