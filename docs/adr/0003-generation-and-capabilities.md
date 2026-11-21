# ADR 0003 · Model integration and native capabilities

**Status** Accepted, 2026-11-21.

**Context** Model generation has variable latency and a user may want to use a local inference server. Generated apps also need access to substantial engines such as a browser.

**Decision** Have the desktop host send the user's request and current source to a configurable chat-completions endpoint. Validate the returned project and place it in the editor for review and execution. Run generated code in an opaque-origin iframe. Expose named capabilities through a small host-controlled interface. The first capability is a browser surface with navigation commands and state events. The web page and generated toolbar have separate profiles.

**Consequences** Apps run locally after generation. Browser content can execute its own scripts and load real sites. A toolbar can be edited without rebuilding the underlying web page. App source stays portable while capabilities with OS effects require deliberate host support. Version 1 hosts a single surface below the toolbar, with downloads, file selection and device access restricted.

**Review trigger** Specify grants, lifecycle, tests and compatibility before adding a filesystem, audio capture, multiple browsing surfaces or persistent guest storage.
