# ADR 0001 · Native workspace and generated documents

**Status** Accepted, 2026-11-21.

**Context** The workspace needs a configurable-size desktop window and apps with graphics and behavior that the host's authors have never anticipated. Reimplementing text entry, accessibility, layout and a graphics language would make each of those a dependency for app generation.

**Decision** Use a native Qt Quick scene for the board and panel controls. Run each generated HTML/CSS/JavaScript document in Qt WebEngine. Authors can use the DOM, SVG, Canvas 2D and WebGL. Qt and Chromium choose their graphics backends for the device. Qt exposes a GPU-backed scene graph through native graphics APIs. [Qt Quick scene graph](https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph.html) · [Qt WebEngine architecture](https://doc.qt.io/qt-6/qtwebengine-overview.html)

**Consequences** App source maps to documented drawing and interaction APIs. The renderer owns batching and device commands. A second app type needs no host registration. Chromium increases the installation footprint and each live web surface consumes memory. Hardware-specific performance remains a measurement to make on target devices.

**Review trigger** Revisit native custom-rendering surfaces when an app needs a measured latency target or device feature unavailable through the existing document runtime.
