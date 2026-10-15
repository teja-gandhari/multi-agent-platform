# NexusAI frontend-only agent update

This agents folder changes the generated application contract to static HTML, CSS, and browser JavaScript.

## Expected generated project files
- `frontend/index.html`
- `frontend/style.css`
- `frontend/script.js`
- `README.md`
- `.gitignore`

## Behavior
- Planner, Researcher, and Developer plan a frontend-only UI.
- Coder generates the UI without a backend, database, API, API keys, external assets, or build step.
- Tester checks required files, asset references, forbidden backend/API patterns, optional Node.js syntax, and serves the UI temporarily for an HTTP smoke test.
- Reviewer approves based on frontend checks.
- Runner starts only a local static HTTP server and returns a URL such as `http://127.0.0.1:8080/`.

## Replace and run
1. Back up your existing `agents` folder.
2. Extract this ZIP in the NexusAI project root and replace the existing `agents` folder.
3. Keep your existing `services`, workflow, `main.py`, and configuration files unchanged.
4. Run NexusAI as usual with a new prompt.

The generated app uses local sample data and may use browser `localStorage`; this is not a shared database. Features requiring real accounts, shared data, server processing, or live external data are demo-only in this frontend-only version.

## Validation performed
- All Python agent files passed `compileall`.
- A synthetic static UI passed the updated Tester.
- The updated Runner started the synthetic UI, returned a local URL, and stopped its child process in the same process session.
- The complete NexusAI LLM workflow was not run here; integration with the rest of the project still needs a real prompt test.
