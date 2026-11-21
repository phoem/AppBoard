# AppBoard

AppBoard opens a resizable 1920 × 1080 desktop workspace. Create an app by describing it to a model or by writing its source. Each running app gets a movable panel with Edit, Save and Close controls. The board starts empty.

## Run on Windows

Double-click **AppBoard.cmd** if the project environment is installed. For a new checkout, install Python 3.12 and run these commands in the project directory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m appboard
```

The dependency list pins PySide6, which supplies Qt Quick and Qt WebEngine. Window dimensions use Qt logical pixels. Display scaling and the window manager determine the physical size. Panels use the board beneath the command bar.

## Create, edit and reopen an app

1. Select **New app** or press **Ctrl+N**. Enter a prompt such as “Draw a constellation editor. Let me click to add stars and connect consecutive stars with lines.”
2. Choose a model endpoint and model, then select **Generate**. A compatible local model server must be running. You can also write or paste a self-contained HTML document in the source editor.
3. Review the draft and select **Run app**. Drag the panel by its title bar or resize it from the bottom-right corner.
4. Select **Edit** to change the HTML, CSS and JavaScript directly or request a revision. **Run app** applies the draft and reloads the generated document. A separate browsing pane retains its page while its toolbar is revised.
5. Select **Save** to write a portable `.appboard` project. **Close** removes the running instance. **Open** or **Ctrl+O** restores the saved design and behavior. Opening the same file twice creates independent instances.

The project contains app source and presentation settings. Variables in memory and browsing sessions last for the lifetime of the instance. Reopening a saved project works offline. Sites in a browser app still require their usual network access.

## Connect a model

Studio accepts a chat-completions endpoint with JSON-schema structured output. It starts with the LM Studio base URL `http://127.0.0.1:1234/v1`. Ollama's local compatibility endpoint is `http://127.0.0.1:11434/v1`. Enter the model ID or leave it blank for discovery. When a server lists multiple models, choose a chat model from the dropdown and select **Generate** again. Studio remembers the endpoint and model after successful generation.

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

Run the complete suite in a Windows desktop session. It opens the native shell, runs JavaScript in Chromium, draws to Canvas, edits and reopens a saved project, and checks a local web page survives a toolbar revision. The tests start an ephemeral loopback HTTP server for model responses and browser content. They require no account, model download or internet connection.

To include the optional live test, set `APPBOARD_LIVE_MODEL` to an installed model ID before running the same command. The test asks the configured server for a small interactive app, clicks its generated control inside Chromium and checks the saved project.

## Project documents

- [Implementation plan and milestone acceptance tests](docs/PLAN.md)
- [App project and browser API reference](docs/RUNTIME.md)
- [ADR 0001 · Native workspace and generated documents](docs/adr/0001-native-workspace.md)
- [ADR 0002 · Editable project files](docs/adr/0002-project-format.md)
- [ADR 0003 · Model integration and native capabilities](docs/adr/0003-generation-and-capabilities.md)
