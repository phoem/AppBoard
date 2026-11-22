# AppBoard

AppBoard opens a resizable 1920 × 1080 desktop workspace. Create an app by describing it to a model or by writing its source. Each running app gets a movable panel. AppBoard automatically saves your apps in a searchable local library. The board starts empty.

## Run on Windows

Double-click **AppBoard.cmd** if the project environment is installed. For a new checkout, install Python 3.12 and run these commands in the project directory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m appboard
```

If you installed the original HTML runtime, rerun the pip install command above in the existing environment. New apps use QuickJS for logic and Qt Quick for native 2D drawing. Qt WebEngine renders website content and older HTML projects. Window dimensions use Qt logical pixels.

## Create, edit and reopen an app

1. Select **New app** or press **Ctrl+N**. Enter a prompt such as “Draw a constellation editor. Let me click to add stars and connect consecutive stars with lines.”
2. Pick a model and select **Generate and run**. The panel opens immediately. Its heading, layout and controls appear as the model finishes drawing sections. The controls become interactive when the main page is complete.
   Try “Build a sketchbook with a drawing page and a gallery.” Opening **Gallery** for the first time asks the model to draw that feature. **Back** returns to the previous page. Subsequent visits reuse the generated page.
3. You can also write a drawing script and select **Run app**. Drag the panel by its title bar or resize it from the bottom-right corner.
4. Select **Edit** to change the visible page or request a streamed revision. **Stop** cancels a build and **Retry** repeats it. Applying a revision restarts that page's script.
5. Close the panel when you're done. **Library** or **Ctrl+O** lets you search by app name or original prompt and reopen the app. Completed pages open offline. An interrupted first build appears as **unfinished** and can resume with **Retry**.
6. To share an app, select **Export** on its panel and send the resulting `.appboard` file. The recipient selects **Library → Import .appboard…** to add an independent, editable copy. Existing project files import the same way.

The library stores app source, the generation brief, presentation settings and completed features. On Windows the database is normally at `%LOCALAPPDATA%\AppBoard\AppBoard\library.sqlite3`. Variables in memory and browsing sessions last for the lifetime of the instance. Websites and first-time generation of a feature still need their usual connections.

## Connect a model

Studio lists models automatically from LM Studio at `http://127.0.0.1:1234/v1`, Ollama at `http://127.0.0.1:11434/v1`, and the **Configured server** if its URL differs. Each entry shows its provider. **Refresh** updates availability. The list includes the IDs that each server advertises, so choose a chat model that supports JSON-schema output. Studio remembers your selection.

| Optional environment variable | Purpose |
| --- | --- |
| `APPBOARD_MODEL_URL` | Initial API base URL including the version path |
| `APPBOARD_MODEL` | Initial model ID |
| `APPBOARD_MODEL_KEY` | Bearer token for the configured base URL |

A generation request sends the prompt and current draft to the selected endpoint. Remote endpoints require HTTPS. Keys stay in the desktop process. **Stop** cancels the client request. A server may finish work already underway. [LM Studio structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output) · [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs)

## Verification

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Run the suite in a Windows desktop session. It checks native rendered pixels, pointer and keyboard input, legacy HTML projects, the save/reopen flow, selection of identically named models on different servers, automatic launch, and page retention during toolbar edits. Loopback fixtures supply model responses and browser content.

To include live inference tests, set `APPBOARD_LIVE_MODEL` to an installed model ID before running the same command. These checks generate a native tally app and a progressive sketchbook, click their controls, and verify that Gallery is generated on first use.

## Project documents

- [Implementation plan and milestone acceptance tests](docs/PLAN.md)
- [ADR 0006 · Local app library and portable copies](docs/adr/0006-local-app-library.md)
- [App project and browser API reference](docs/RUNTIME.md)
- [ADR 0005 · Progressive pages and first-use generation](docs/adr/0005-progressive-pages.md)
- [ADR 0004 · Native 2D app rendering](docs/adr/0004-native-drawing.md)
- [ADR 0001 · Native workspace and generated documents](docs/adr/0001-native-workspace.md)
- [ADR 0002 · Editable project files](docs/adr/0002-project-format.md)
- [ADR 0003 · Model integration and native capabilities](docs/adr/0003-generation-and-capabilities.md)
