# API entry points

`server/http.py` is the executable routing implementation; feature modules contain the associated typed validation and current-rights checks. The browser client demonstrates the corresponding authenticated request construction. This brief entry note is not an exhaustive endpoint specification.

- `/api/providers` reports configuration/availability/testing separately for the core integrations.
- Session creation and normal Creator/Viewer entries establish scoped actor access; use the UI rather than inventing or extracting capability tokens.
- The Twitch connection action retrieves Helix metadata using backend-only app credentials. It does not access chat, audio, images or publish to Twitch.
- Editorial output requires current source/revision/rights and creator approval. Public output is distinct from private viewer work.

Do not publish invitations, bearers, private provider receipts or database rows. No development session data is a required API input. For installation and current limitations see [setup](../docs/SETUP.md).
