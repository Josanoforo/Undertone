# Source layout

- `server/`: Python entry point, HTTP routing, persistence, access/revision controls, providers and feature modules. `server/__main__.py` enters through the recovery-startup guard.
- `client/`: current source HTML, JavaScript and CSS, including the Browser Source overlay. No build step is required. Set `APP_CLIENT_DIR` to this directory.
- `scripts/`: finite evaluator packager, optional setup, launch/readiness, budget and private backup/recovery helpers. Read each script before executing it.
- `contracts/`: public entry-point, stack and gateway notes.
- `docs/`: setup, capabilities and notices. Optional dependencies remain explicit.

Runtime creates private `data/` and `.runtime/` directories, excluded from Git. No development sessions, logs, databases, credentials, original Git history or cached models are part of this source tree. See the root [README](../../README.md).
