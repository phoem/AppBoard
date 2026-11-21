# Authoring an AppBoard app

## Native drawing projects · version 2

New apps store `version: 2`, `name`, and a JavaScript `script` in the same portable JSON file. The size limit is 512 KiB. Optional `browser` and `toolbarHeight` fields have the same defaults as version 1. Each running instance owns its own script state. The LLM uses this same interface for new designs and edits.

```javascript
let stars = [];
function input(e) {
  if (e.type === "down") stars.push([e.x, e.y]);
}
function draw(g, w, h) {
  g.clear("#182536");
  for (const [x, y] of stars.slice(-200)) g.circle(x, y, 3, "#ffdc87");
  g.text(12, h - 32, stars.length + " stars", 16, "white");
}
```

| Operation | Arguments and behavior |
| --- | --- |
| `g.clear(color)` | Discard earlier drawing operations and fill the panel. |
| `g.rect(x,y,w,h,color,radius=0)` | Filled rectangle with optional rounded corners. |
| `g.circle(cx,cy,radius,color)` | Filled circle around its center. |
| `g.line(x1,y1,x2,y2,color,thickness=1)` | Stroked segment. |
| `g.path(d,fill,stroke="transparent",thickness=1)` | Vector shape using SVG path-data syntax, including curves. |
| `g.text(x,y,value,size=16,color="#151918")` | Plain text positioned by its top left, with size in logical pixels. |
| `g.image(x,y,w,h,png)` | Draw an embedded PNG data URL, up to 2048 × 2048 and 400,000 URL characters. |
| `g.animate()` | Request another draw after roughly 16 ms. Use elapsed time for motion. |

Colors use Qt names, `transparent`, or hex such as `#RRGGBB`. Every draw produces the full scene in paint order. Width and height track the surface size. `input(e,g,w,h)` receives pointer `down`, `up` and `move` events with coordinates and a buttons bitmask, `wheel` with coordinates and delta, and `key` with text, Qt key code and modifiers. Click a surface to give it keyboard focus. Draw custom controls and handle their hit regions in the script.

In browser mode, the drawing surface occupies the toolbar area. `g.browser` provides URL, title, loading and history flags, and `navigate(url)`, `back()`, `forward()` and `reload()` commands. Handle commands in input callbacks or guard one-time actions. A page state change requests a redraw.

Each script context has a 16 MiB memory limit, a 256 KiB stack limit and a 50 ms execution budget per call. Frames support up to 512 drawing operations. Scripts receive drawing, input and browser data. The host retains control of files, network credentials and Qt objects. A runtime error stops that script and appears in its panel.

## Legacy HTML projects · version 1

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
