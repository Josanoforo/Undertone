# Setup and optional prerequisites

Use Windows x64, Python 3.12.x and a current Chromium/Edge browser. Run from the repository root. Follow the root README for a fresh local start; do not inherit another installation's data directory or secrets. No `.env` loader is provided. Select `APP_CLIENT_DIR` explicitly so a stale generated `client/dist` cannot take precedence.

## Core and configuration

The core HTTP/SQLite backend uses the standard library. No `pip install` or Node toolchain is needed to open the local UI. `package.json` is an optional command wrapper; `python -m server` is the actual entry point. Preserve technical module/storage IDs. Configuration examples contain non-secret settings and blank credential names only.

The maintained Windows launcher is `scripts/Start-Local.ps1 -Foreground`; it checks the chosen loopback port and writes private run state under `.runtime/`. Direct `py -3.12 -B -m server` is sufficient for the basic evaluator start. Do not launch over an existing service. The scripts do not automatically install providers or download models.

## Generation

For Ollama, separately install the service and make the configured `qwen3.5:9b` model available; use the exact model rather than silently substituting an engine. Startup without the model still permits the core UI, but generation is unavailable. For Claude, select `APP_AI_PROVIDER=claude` and supply `ANTHROPIC_API_KEY` only to the backend process through a trusted secret prompt or manager. Do not put keys in commands, README, examples or Git. `scripts/Provision-ClaudeCredential.ps1` is the optional Windows user-bound DPAPI provisioning path; its encrypted output is private. Review the application's budget/admission limits before enabling hosted inference. No paid operation is needed for core setup.

## Speech recognition

Explicit optional installation:

```powershell
.\scripts\Setup-Asr.ps1
```

This installs `scripts/ASR_REQUIREMENTS_LOCK.txt`, downloads only the files/revision pinned by `scripts/ASR_MODEL_MANIFEST.json`, and verifies file sizes and SHA-256. It creates a private virtual environment/cache. Set `ASR_PYTHON` and `ASR_MODEL_PATH` to the verified paths printed by setup. `ASR_LANGUAGE` is independent of UI language. No dependency installation or model download was repeated for this candidate.

## Local speech output

The source adapter `server/waves17_tts_local.py` expects `.runtime/mesa02/w17-local-voice/venv/Scripts/python.exe`, CPU `sherpa-onnx==1.12.40` and `sherpa-onnx-core==1.12.40`, plus the exact two model folders, tokens and eSpeak data recorded by the distribution manifest. It produces buffered WAV, not progressive streaming. Installation is separate; these assets are not copied from the developer machine.

The Python wheel lock is complete as metadata in `scripts/LOCAL_VOICE_WINDOWS_CP312.lock.txt` and `scripts/LOCAL_VOICE_DEPENDENCY_LOCK.json`. The installer and local model manifest are held and absent: exact Spanish weight traceability and the source/build/notices for the archived eSpeak data remain unresolved. A fresh checkout cannot claim local Listen is reproducible. See [local distribution](LOCAL_VOICE_DISTRIBUTION.md) and [third-party notices](THIRD_PARTY_LOCAL_VOICE_NOTICES.md). Read mode and other core features remain distinct.

## Hosted speech output

Keep `APP_ENABLE_RELEASED_HOSTED_PROFILE` unset in a clean evaluator checkout. The existing runtime facade remains as required application source; its operator-specific profile loader/private authorization is not distributed. The held proposed facade adaptation is absent. Released loader/transport/example/provisioning components are included as inert components, not a functioning hosted feature. No account, credential, dated budget authorization or cumulative quota reservation is supplied. Do not change budget/admission policy to activate it. See [optional speech boundaries](DISTRIBUTION_ADAPTATIONS.md).

## Twitch and overlay

OBS Browser Source is an optional external tool. Supply only authorized, approved app content to the overlay. For the separate Helix metadata action, supply the evaluator's own backend app credentials. No Twitch Extension, viewer OAuth, chat capture or automatic stream capture is claimed. The submission demonstration and its public video link belong to the owner's release materials.

## Recovery and remote viewers

Use [recovery](delivery/waves30/RECOVERY.md) for private backup/isolated recovery helpers. Never publish a database or restore over a live installation. Remote access requires the separately configured viewer gateway, shared process secret, exact public HTTPS origin and independent TLS ingress. This source candidate supplies neither hosting nor a usable invitation to the developer's service.

## Documentation and current source boundary

Use this SETUP for a fresh checkout. OPERATIONS.md preserves the earlier operating manual verbatim; its historical evidence links refer to the original operator checkout and are not bundled. The finite legacy evaluator packager selects its own270-source inventory, a subset of this repository, and does not define this full Git source distribution. No new ZIP was built. See [release scope](RELEASE_SCOPE.md).

## Brand assets and fonts

The released Undertone v1.0 Tangerine Block client includes exact logo/favicon assets and local Fraunces SemiBold600 with its OFL notice. Tokens also retain a Google Fonts CSS import for other requested families/weights, so full typography has a network dependency and fallbacks when unavailable. The included CSP source permits those style/font origins; this does not assert runtime deployment. Six equivalent before/after comparisons remain unperformed; no additional visual acceptance is claimed.

## Regional OCR and sentence workflow

Regional OCR uses the installed Windows.Media.Ocr recognizer through the standard C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe path. The worker source is included; no recognizer/language pack is installed by setup. It processes only the selected PNG crop; missing recognizer, unsupported rotation or failure remains unavailable, without automatic retry. This is regional OCR, not full-video or live understanding.

Final text can be split into conservative punctuation units and forwarded through existing Creator/Viewer translation admission. Sentence playback is explicitly requested and buffered; native streaming and word alignment are unavailable. The source union/admission/player checks do not establish newly generated live translated sentence audio; no such generation was performed for this release.
