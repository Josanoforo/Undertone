# Optional speech setup

The product code can use local neural speech when its optional assets are installed, but the proposed local setup files are held and are not in this candidate allowlist. ElevenLabs hosted speech is unavailable: the `server/waves17_hosted_facade.py` proposal is held because its reservation cannot run in a clean evaluator checkout. Do not enable `APP_ENABLE_RELEASED_HOSTED_PROFILE` expecting a working hosted path. That flag is an explicit opt-in only; it does not verify an account, quota, rights, or pricing.

## Hosted configuration components (inert only)

The included `config/hosted-account.example.json` is deliberately unconfigured. Its false verification flags, blank identifiers/revisions, and zero quota/rates are not account evidence and must not be changed to claim verification.

On Windows, `scripts/Provision-ElevenLabsCredential.ps1` with no switch prints a **NOOP** and writes nothing. Running it with `-Execute` prompts for an API credential without echoing it and writes a DPAPI `CurrentUser` protected blob to `.runtime/credentials/elevenlabs-key.dpapi`. It does not contact ElevenLabs, verify access, select a voice, or set a quota. Keep the credential and resulting private files out of source control and logs.

A future hosted release would also require `.runtime/credentials/verified-account.json`, which is not supplied here, with its digest supplied as `APP_HOSTED_PROFILE_SHA256`, plus a portable evaluator-owned budget and quota reservation implementation. This candidate does not provide that complete feature. Hosted speech must remain unavailable until that integration is released; local speech is never selected automatically as a hosted fallback.

## Local speech

The optional local EN/ES setup remains **HOLD_EXACT_COMPONENT_TRACEABILITY_NOT_INSTALLABLE**. Its complete Windows x64 / CPython3.12 runtime wheel lock is available in `scripts/LOCAL_VOICE_WINDOWS_CP312.lock.txt` and `scripts/LOCAL_VOICE_DEPENDENCY_LOCK.json`: exactly sherpa-onnx1.12.40 and sherpa-onnx-core1.12.40, with exact wheel URLs, platform markers, published SHA256 and verified PEP658 metadata. The held installer proposal uses the hash-bound lock rather than an open dependency resolution.

Both compressed voice archives now have corroborated official GitHub digests. EN's original voice has a public-domain declaration and its converted public LFS identity matches the required model. ES's public converted weight hash differs from the adapter-required hash; the dataset/Space Apache labels do not resolve that exact artifact. The originating revision/notices/corresponding source of the eSpeak data in the selected archives also remain unestablished. Runtime source Apache, voice/dataset terms, MIT phonemizer code and GPL eSpeak are separate; do not advertise the whole payload as Apache-only.

See `docs/LOCAL_VOICE_DISTRIBUTION.md` and `docs/THIRD_PARTY_LOCAL_VOICE_NOTICES.md` for exact evidence and remaining limits. The mutually consistent installer/manifest replacement is held, with ordinary invocation NOOP and `--execute` refusing before any effect. Do not remove that refusal by acknowledgement or guessed license fields. No runtime, model, private environment or credentials are shipped. Undertone remains all rights reserved. Prior17 synthetic checks are reused; no installation, synthesis or new availability claim is made. Preserve the independent hosted holds and owner17's current section verbatim when merging this local section.
