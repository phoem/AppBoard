# Authoring an AppBoard app

## Progressive native projects · version 3

New projects keep a native main-page script, a `brief` containing the original request, and a `features` object. Each feature key maps to a completed version 2 native page. The entire file uses the same 512 KiB budget. Model endpoints and credentials come from local settings.

For generation, the server streams a page name, drawing sections, browser settings and an input handler. On the main page each drawing section has its own block. A custom feature’s `sections` array contains ordered code fragments sharing one `draw(g,w,h)` body. Layout variables and loops can span fragments. The separate input handler shares state through `g.data`. Input becomes active after validation. **Stop** restores the previous page and **Retry** repeats the pending request.

For a plain read-only list or thumbnail grid, a generated navigation button can prefix its brief with `Browse collection:`. AppBoard also recognizes short browsing requests from older apps, such as `View Gallery`. The model returns five strings. `name` is the heading. `collection` names an array in `g.data`. A blank key selects the sole known array, or the feature ID if the choice is ambiguous. `labelField` names the display field for object entries. String entries display directly. `imageField` selects an embedded PNG field for thumbnails, or an empty string for a text list. `emptyText` supplies the empty-state message and defaults to “No items yet.” AppBoard compiles the description to editable native drawing and scrolling code that travels with the app. Custom features and revisions use the full drawing and input format.

For a new main page or feature, Qt paints a temporary layout with the request or feature name before the model responds. The streamed title updates the heading. AppBoard tries drawing prefixes in a disposable interpreter and keeps the last valid frame while a custom feature is completing a block or defining a helper. Invalid native operations can trigger one correction early. The full page must pass drawing and input validation. After a correction, hover over the panel title to see which stage failed and the first error. This detail stays in the session until its next generation starts.

For the standard loopback LM Studio server on port 1234, the client checks whether the selected model advertises switchable reasoning. It requests a direct answer for initial page builds when supported. Corrections use the provider's normal settings. Other endpoints keep their usual inference settings. [LM Studio model capabilities](https://lmstudio.ai/docs/developer/rest/list)

Use `g.featureButton(x,y,w,h,label,id,description,color)` in a drawing section to draw a feature button with built-in pointer handling. Custom click or keyboard handlers can use `g.openFeature(id, description)`. Choose a stable lowercase ID starting with a letter, with up to 64 letters, digits, hyphens or underscores. The description tells the model what to build on first use. The host supplies a Back control. Each app supports up to 64 saved features.

```javascript
function draw(g, w, h) {
  g.clear("#182536");
  g.text(16, 12, "Sketchbook", 24, "white");
  g.featureButton(16, 56, 140, 40, "Gallery", "gallery",
                  "Draw a grid of sketches from g.data.sketches.", "#387654");
}
```

`g.data` is a per-instance JSON object shared between pages, limited to 64 KiB. A new feature request includes the requested behavior, app and calling page names, palette, existing feature IDs and shared data key names. Revisions include the page being edited. Runtime data values remain local. Before accepting a generated page, AppBoard exercises up to four label positions in a disposable interpreter. Browser commands, feature requests and data changes from this check are discarded.

**Edit** changes the visible page. AppBoard saves each accepted page to the app’s SQLite record. Reopening from **Library** starts on the main page. Visiting a saved feature works offline. **Export** writes all completed pages together. Importing a file creates a new library entry.

## Native drawing projects · version 2

Previously saved single-page native projects retain their format for manual edits. A successful streamed revision or a first generated feature upgrades the library copy to version 3. Export writes the current version to the chosen file.

Single-page files store `version: 2`, `name`, and a JavaScript `script`. The size limit is 512 KiB. Optional `browser` and `toolbarHeight` fields have the same defaults as version 1. The following drawing operations also apply to every page in version 3.

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
