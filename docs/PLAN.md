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

### Complex custom feature benchmark

Run the paired desktop benchmark from the project directory with a running LM Studio server.

```powershell
$env:APPBOARD_BENCH_MODEL = 'google/gemma-4-e4b'
.\.venv\Scripts\python.exe -B -m unittest tests.test_custom_features -v
```

Each trial starts with a fresh app and an isolated SQLite library. Timing starts at feature navigation. The benchmark records the first presented Qt frame with generated content, the time AppBoard activates the feature, and the number of model requests. The browser must accept a typed URL, load a loopback page in Chromium, follow a link, go back and go forward. The rock-core logger must preserve the order of three entries including a duplicate, then undo only the final entry. Both use the custom drawing path. A first-pass success requires all interactions and exactly one model request.

The final three paired runs used LM Studio and `google/gemma-4-e4b` on Windows.

| Generated feature | First drawing, all trials | Passed on first request | Active, successful trials | First site loaded |
| --- | --- | --- | --- | --- |
| Reference browser | 3.81–4.21 s | 3 of 3 | 8.57–9.75 s | 8.84–10.11 s |
| Rock-core logger | 1.98–3.42 s | 1 of 3 | 14.02 s | — |

One unsuccessful logger emitted invalid JavaScript and the other called an unavailable drawing method. Both failed the automatic correction. The successful logger appended Clay, Sand and Clay in order and removed just the last entry on Undo.

On Windows with the running Gemma model and fast inference, two of three browsers passed in an initial paired run. The successful browsers first drew at 3.86 and 4.79 s, activated at 9.43 and 10.11 s, and finished the first local page load at 9.69 and 10.42 s. The third activated but omitted the requested address placeholder. The three loggers drew within 2.13–3.05 s and all failed validation on unsupported drawing methods. In three earlier logger trials with the same feature prompt, one passed on the first request in 22.49 s. In that earlier batch the Windows test process exited on Chromium startup when unittest discovery used the pattern flag. The same exit reproduced with a fixed browser fixture. Use the named-module command above to avoid the launcher issue.

To compare provider defaults, set `APPBOARD_BENCH_PROVIDER_DEFAULT=1` for the benchmark. This omits the optional fast-inference override for that run. In three paired trials, one logger passed in 15.56 s. Two browsers drew toolbars without enabling Chromium. The third loaded the typed address in 15.35 s but the original test stopped at its decorated Back label, so its history behavior was unverified. First browser drawings took 11.46–16.83 s in this mode. The benchmark now accepts common address hints and arrow decorations, and still checks the resulting page after each action.

### Ordered edits and new feature checks

The previous logger benchmark passed once in three trials. The two rejected programs had a JavaScript syntax error and a call to an unavailable drawing method. Earlier outputs also duplicated a press or cleared every entry during Undo. Ordered-list briefs now have a structured choice alongside custom drawing code. The host compiles each requested operation and the model provides the labels, entry values and separator. See [ADR 0005](adr/0005-progressive-pages.md).

Three fresh paired desktop trials used the same local Gemma model and original logger prompt. All timings start at feature navigation and include validation.

| Feature | First drawing | Ready | One-response behavioral passes |
| --- | --- | --- | --- |
| Rock-core logger | 2.38–2.46 s | 2.47–2.56 s | 3/3 preserved Clay, Sand, Clay and removed only the last Clay |
| Dispatch queue | 2.60–2.88 s | 2.70–3.02 s | 3/3 preserved duplicate arrivals, served the oldest and reset before accepting new arrivals |

The queue's first exploratory build missed the requested display format. A replay produced an empty separator and renamed controls. The final generator constrains explicit quoted delimiters and unambiguous action labels in its response schema. Exploratory runs also exposed a separate problem in free-form drawings. The model sometimes returned an anonymous event function where the host expected its body. New feature scripts can now call that function in the existing sandbox. A survey caliper failed on its first-ever build and later passed in one request at 12.55 s, drawing the tested line and displaying its 50-pixel length.

A mirror-stamp sketchpad needed a correction on its first build. In a later one-response run it retained all four original and reflected marks after two clicks and was ready in 7.40 s. Blank sketchpads receive clicks during the benchmark even if they begin with no visible marks.

The held-out signal pad used append values different from its button labels. The first build activated in 3.40 s with one response, but the test stopped before clicking because it expected “Dash” and the model drew “Dash (-)”. After allowing that visible label in the test, a fresh generation passed with one response. It first drew at 3.13 s and was ready at 3.21 s. Real clicks encoded `-.-`, erased the last symbol, reset the sequence and entered a new dot. The original build’s behavior was unverified.

### Native 2D authoring and model discovery · implemented

New projects use version 2 drawing scripts. The runtime maps their primitives to native Qt Quick items. Version 1 documents keep their reader and renderer. Studio discovers provider-qualified model IDs and runs a valid generated native app as soon as the model completes its response. Coverage includes native pixels and input, save/reopen, resource limits, browser toolbar revisions, multi-provider routing and a live LM Studio generation test. See [ADR 0004](adr/0004-native-drawing.md).

| Milestone | Acceptance test |
| --- | --- |
| Configurable layout and multiple browser surfaces | Generate vertical tabs or a split browser. Move the toolbar while retaining page history and entered form data. |
| Durable app-owned state | Offer per-project storage with explicit export, deletion and size limits. A generated scorekeeper can resume a match after restart. |
| Visual editing and history | Change a selected element's style, revise it by prompt, undo both edits and reopen the resulting source. |
| Distribution and hardware validation | Package a signed desktop build. Verify DPI, multi-monitor placement, WebGL and frame timing on representative GPUs. |

Each new capability needs a documented interface, an integration test using an unfamiliar app, and an ADR when it changes the runtime or persistence boundary.
