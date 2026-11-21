# Authoring an AppBoard app

## Project version 1

A `.appboard` file is a UTF-8 JSON object, limited to 512 KiB including its serialized source. The host validates every project before running or saving it.

| Field | Contract |
| --- | --- |
| `version` | Integer 1. Unknown versions are rejected. |
| `name` | Nonempty title up to 100 characters. |
| `html` | Self-contained, nonempty HTML document containing styles, scripts and inline assets. |
| `browser` | Optional boolean. Defaults to false. Enables one live browsing pane below the generated document. |
| `toolbarHeight` | Optional integer from 32 to 400 logical pixels. Defaults to 80. Applies in browser mode. |

The generator supplies every field. The reader accepts the optional defaults and rejects unknown fields. For a format change, update the reader, generator schema, reference and compatibility tests together.

## Drawing and behavior

Write ordinary JavaScript inside the document. Use HTML controls for keyboard and pointer interactions, SVG for scalable shapes, Canvas 2D for freehand graphics, and WebGL for shaders where the graphics driver supports it. Layout dimensions are the app panel's current dimensions. Use CSS or a ResizeObserver to respond to panel resizing. Inline resources travel with the project. External imports and ordinary network requests are filtered.

The host runs the document inside a sandboxed iframe with an opaque origin. Its outer document owns the Qt WebChannel. Each instance has an off-the-record profile. A source revision creates a fresh document, so scripts should initialize their own runtime state. The editor and user-selected files live in the host. Treat this developer build as a local authoring tool. Resource quotas and distribution hardening are follow-up work.

## Browser capability

Enable the browser checkbox or generate a project with `browser` set to true. The host allocates a separate web view with its own off-the-record profile. Its network content runs independently of the generated toolbar. Navigation accepts HTTP and HTTPS. Remote pages receive no AppBoard bridge.

| Call | Behavior |
| --- | --- |
| `AppBoard.browser.navigate(url)` | Navigate the browsing pane to an address. |
| `AppBoard.browser.back()` / `forward()` | Move through this pane's history. |
| `AppBoard.browser.reload()` | Reload the page. |
| `AppBoard.browser.state` | Latest URL, title, loading flag and history availability. |
| `AppBoard.browser.subscribe(fn)` | Receive the current state and subsequent updates. Returns an unsubscribe function. |

For example, a generated toolbar can bind its controls directly to the live page.

```html
<form id="nav"><button type="button" id="back">Back</button>
  <input id="address" aria-label="Address"><button>Go</button></form>
<script>
  const browser = AppBoard.browser;
  const input = document.querySelector("#address");
  const back = document.querySelector("#back");
  back.onclick = () => browser.back();
  document.querySelector("#nav").onsubmit = event => {
    event.preventDefault();
    browser.navigate(input.value);
  };
  browser.subscribe(state => {
    back.disabled = !state.canGoBack;
    if (document.activeElement !== input) input.value = state.url;
  });
</script>
```

An app can keep its browsing pane while applying a new toolbar design. Closing the app or switching off its browser capability ends that page session. This version supports one browsing pane per app. Multiple panels can browse independently.
