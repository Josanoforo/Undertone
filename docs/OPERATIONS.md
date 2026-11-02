# Undertone — local startup

This is a local Python 3.12 backend. The product defaults to English; generated output honors an explicit language, and user inputs, quotations and audio language are preserved. The CLI development model is independent of the product AI provider. The named Phase 2 R7 example and six format cases received case-level review across frozen candidates; overall acceptance and the current source/runtime state remain separate from the startup check below.


For the working-tree layout and command scope, see the [repository map](docs/architecture/REPOSITORY_MAP.md). Waves 1–12 were owner-closed with their recorded limits; Waves 13–14 are authorized and executing. Current dispositions and ownership are in the [execution dispatch](docs/planificacion/WAVES13_14_EXECUTION.md) and [parallel matrix](sessions/central/WAVES13_14_RECOVERY/PARALLEL_OWNERSHIP.md). Historical delivery packages are separate snapshots, not current acceptance or deployment evidence.

## Create a local evaluator copy

Install Python 3.12 and verify `py -3.12 --version`. From this repository root, create a new output directory with the current packager:

```powershell
py -3.12 -B scripts/waves30-package.py --destination docs/delivery/waves30/exports/evaluator-ola2-01
```

Use a new destination for each export; the exporter refuses an existing destination and reparse points. It excludes credentials, database/WAL/SHM files, browser profiles, private logs, and execution state. Make the definitive export after changes to included inputs finish in Ola 1; if a source changes during staging or writing, the export is rejected.

The destination is an export folder containing `evaluator.zip` and an external `MANIFEST.json`. The manifest records the ZIP SHA-256 and the included file paths, byte counts, and SHA-256 hashes; it is not inside the ZIP. The ZIP contains the prepared source snapshot, including `docs/delivery/waves30/EVALUATOR_SETUP.md`, but excludes this repository README, the exporter, and the legacy `docs/delivery/package/runtime_sources.json` manifest. The previous setup exporter produced a ready-to-run directory tree; its `.runtime` destinations are no longer accepted, and `scripts/setup_evaluator.py` now delegates to the current ZIP builder. The runbook warning that `scripts/setup_evaluator.py` selects an incomplete legacy inventory is historical; that source-repository adapter now delegates to the current builder and is not included in the ZIP. Follow the included `EVALUATOR_SETUP.md` for package instructions.

Extract the ZIP into a new private directory, then use the extracted root (the directory containing `server/` and `client/`) for all evaluator commands:

```powershell
$export = (Resolve-Path 'docs/delivery/waves30/exports/evaluator-ola2-01').Path
$privateRoot = Join-Path (Get-Location) 'evaluator-ola2-01-private'
Expand-Archive -LiteralPath (Join-Path $export 'evaluator.zip') -DestinationPath $privateRoot
Set-Location $privateRoot
$env:APP_HOST = '127.0.0.1'
$env:APP_PORT = '18765' # choose a free port; do not stop or alter a shared service
$env:APP_DATA_DIR = (Join-Path (Get-Location) 'data')
py -3.12 -B -m server
```

Only run the last command when you intend to start the evaluator locally. The selected port must be free; this procedure does not touch a service already using another port. Keep the extracted tree and its `data` directory private. Stop the foreground process with Ctrl+C. The archive is a local source snapshot, not deployment, provider availability, AI quality, Twitch broadcast, or acceptance evidence. Packaging does not install dependencies, download models, contact providers, or execute the service. Use the packaged `docs/delivery/waves30/EVALUATOR_SETUP.md` for the complete evaluator instructions.

After the backend is ready, open `http://127.0.0.1:18765/` (or the port you selected).

For a private backup and isolated recovery rehearsal from the exported root, substitute a fresh name each time:

```powershell
py -3.12 -B scripts/backup_sqlite.py --source data/companion.sqlite3 --destination .runtime/backups/evaluator-01.sqlite3
py -3.12 -B scripts/recover_sqlite.py --source .runtime/backups/evaluator-01.sqlite3 --name evaluator-restore-01
py -3.12 -B scripts/recover_sqlite.py --source .runtime/backups/evaluator-01.sqlite3 --name evaluator-restore-01 --execute
```

Use an online SQLite backup, not a live DB as the restore input. The last command creates an isolated clone, never replaces the live database, and refuses an existing recovery name. Keep backups private. Recovery has separately reported [independent synthetic checks](docs/validacion/mesa04/PHASE2_R1_R2_INDEPENDENT.md) in the source repository; those checks do not establish acceptance of every recovery scenario.

## Prepare and start

For a packaged evaluation, open PowerShell in the extracted evaluator root (the directory containing `server/` and `client/`). Commands and included scripts below must run from that root unless a section says otherwise. For source maintenance, use the repository root.

```powershell
python --version
```

### Windows prerequisites

One Windows installation option requires winget. Install the Python 3.12 package, reopen PowerShell, then confirm that Python 3.12 is first on PATH:

```powershell
winget install --exact --id Python.Python.3.12 --version 3.12.10
```

After reopening PowerShell, run `python --version`. The launcher requires Python 3.12. See the [Microsoft package manifest](https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/p/Python/Python/3/12/3.12.10/Python.Python.3.12.yaml).

For the optional local Ollama provider, follow the [official Windows installation instructions](https://docs.ollama.com/windows). After installing and running Ollama, explicitly download the model already named in this app's configuration:

```powershell
ollama pull qwen3.5:9b
```

If that model is unavailable, do not substitute another engine. Ollama is not required for Claude.

Optional local ASR setup, run from the extracted evaluator root, installs the project's pinned environment and model:

```powershell
.\scripts\Setup-Asr.ps1
```

The copied `scripts/ASR_MODEL_MANIFEST.json` includes historical `path` and `download_and_hash_seconds` observations; neither configures the model location. The downloader derives its cache and fresh model path from the current evaluator root and verifies the pinned files. ASR setup requires network access; the model is about 484 MB, and the Python environment and package cache require additional disk space. Its temporary and cache files are kept under the project runtime. These optional installations and downloads were not executed in this phase; the launcher itself performs no installation or download.

For Claude on a fresh Windows account, explicitly provision a previously obtained credential once:

```powershell
.\scripts\Provision-ClaudeCredential.ps1 -Execute
```

The prompt uses hidden SecureString input and Windows user-bound DPAPI; the encrypted file stays under this app and an existing credential is never overwritten. Provisioning is not a provider call. Never put a real credential in a command, document, example file or log. The Windows launcher decrypts it in memory for the child process. Direct `python -m server` uses a separately configured process environment and is not the DPAPI launcher.

From the extracted evaluator root, keep `APP_DATA_DIR` pointed at its private `data` directory and set `APP_PORT` to a free loopback port before using the launcher below. It defaults to port 8765 if unset; do not start a second backend on a port already in use. These are evaluator instructions and do not start a service during package creation.

Choose one provider only when the target port is free:

```powershell
.\scripts\Start-Local.ps1 -Provider claude
# Alternative: an already installed local Ollama service and model
.\scripts\Start-Local.ps1 -Provider ollama
```

The launcher binds `127.0.0.1:8765` by default, records a run manifest and logs under `.runtime/run/`, and checks direct HTTP, process identity and the exact established socket owner. Its preflight includes an exclusive bind probe; it never automatically stops a child after a readiness error. After readiness, open `http://127.0.0.1:<selected-port>/` (port `18765` in the example above; `8765` only when `APP_PORT` is absent). To inspect an existing run without starting another backend or changing its manifest or database:

```powershell
.\scripts\Readiness-Local.ps1 -RunName <recorded-run-name>
```

The JSON separately reports `httpReady`, `healthOk`, `processIdentityVerified`, `ownershipVerified` and `ownershipMethod`. HTTP alone does not establish ownership. On the observed Windows host a listener row had state 0 for an unknown reason; the direct established-tuple check does not claim the state is LISTEN. The recorded cwd is not independently observed and disk hashes do not prove loaded memory. The older source-repository-only `Verify-RunningLocal.ps1` (not included in the evaluator export) has separate backup/adoption behavior and requires a strict LISTEN owner; stop and update guards retain their strict checks and can refuse a service on this host. Do not infer a safe stop from readiness alone.

## External viewer gateway

The Phase 3/4 gateway is a loopback proxy and does not provide HTTPS or hosting. Configure both backend and gateway with the exact public HTTPS origin and the same process-only random gateway secret; do not put the secret in a file or command line. The backend must run a core version enforcing viewer-only gateway authority. A trusted independently provisioned ingress must terminate TLS, preserve Host and Origin, strip forwarding and marker headers, and route only to the gateway. Do not expose the backend. Run `scripts/Start-Gateway.ps1` for configuration and bind preflight, then `scripts/Start-Gateway.ps1 -Execute` to start the gateway in the foreground after the backend and ingress have been configured. Preflight does not prove those dependencies or remote access. See [gateway contract](contracts/GATEWAY.md) for exact requirements, retention, rotation and recovery. The new candidate is not yet integrated or accepted. A bounded same-host synthetic Quick Tunnel HTTPS smoke passed after a delayed Windows DNS resolution; the gateway contract records the earlier DNS failures and remaining limits. Remote-device acceptance is not established.
## Configuration and limits

`.env.example` documents variable names only; neither launcher nor backend automatically loads a dotenv file. Do not populate it with secrets. The Windows Claude launcher selects `claude-sonnet-5-5`, fixes the M02 ledger under `.runtime/mesa02`, and passes a total ceiling of USD 0.50 and 24 calls to the child for the final journey. It does not honor alternative ledger/cap/count environment settings for that launch. Existing reservations and uncertainty remain in the ledger; never reset or refund them. Provider requests may incur charges and reservation estimates are not invoices. Claude sends questions, attempts, selected authorized context and editorial summaries to Anthropic; its adapter rejects images. Configuration, availability and a successful real test are distinct.

Ollama defaults to local `http://127.0.0.1:11434` and `qwen3.5:9b`; it requires no external API key. Optional local ASR uses the existing prepared interpreter/model or explicit settings; the prepared installation defaults to English and an explicit `ASR_LANGUAGE` is preserved. Speech recognition language is independent of interface language. Twitch metadata uses separate backend-only app credentials. Local loopback is not remote access; external viewer access requires the separately provisioned HTTPS ingress and the viewer-only gateway described below.

The [API contract](contracts/API.md) and [stack notes](contracts/STACK.md) describe the application. The launcher does not download or load `.env`. Startup and health checks do not prove AI quality, UI accessibility, Twitch broadcast or full product acceptance.

## Isolated SQLite recovery rehearsal

Keep backups and recovery outputs private under `.runtime` (ignored by Git). Create a consistent online backup with `scripts/backup_sqlite.py`; never use a live database as the recovery source. Validate without writing, then explicitly create a fresh isolated clone:

```powershell
python scripts/recover_sqlite.py --source .runtime/your-backup.sqlite3 --name unique-rehearsal
python scripts/recover_sqlite.py --source .runtime/your-backup.sqlite3 --name unique-rehearsal --execute
```

The tool checks schema version and required table structure, integrity, foreign keys and aggregate equality, and verifies the backup hash. It rejects uncheckpointed WALs and journals, existing outputs and reparse ancestry. Failed artifacts are retained for inspection; it never promotes or replaces live data. `APP_DATA_DIR` in the invoking environment is excluded, but another process's configuration cannot be discovered by this offline tool: the operator must select a private standalone backup and a recovery location unused by any process. This is a local snapshot restoration check, not clean-machine setup, UI recovery, remote delivery or universal security.

## Historical operational notes (original cuts, retained verbatim)

### Proveedor Claude preparado sin conexión

Ollama sigue siendo la opción local predeterminada. `APP_AI_PROVIDER=claude` selecciona explícitamente Claude: preguntas, intentos y contexto de fuentes autorizadas se enviarían a Anthropic. Las imágenes se rechazan; no se envían. El modelo preparado es `claude-sonnet-5-5`; la preparación no demuestra disponibilidad ni uso satisfactorio. El estado no hace inferencias. La clave se proporciona en `ANTHROPIC_API_KEY` al proceso; el runner Windows preparado la descifraría con DPAPI en memoria y la pasaría solo al hijo. No se registra en el ledger.

El presupuesto M02 predeterminado conserva reservas hasta USD 0.50 y ocho llamadas; errores inciertos no liberan reservas. `APP_CLAUDE_LEDGER` debe estar bajo `.runtime`; `APP_CLAUDE_CAP_USD` admite hasta USD 1.50 y `APP_CLAUDE_MAX_CALLS` hasta 64. El smoke M02 fija USD 0.50 y ocho llamadas con ledger constante; M04 usa ledger independiente y cap USD 1.50 explícito. Nunca se reinician las reservas para repetir una prueba. Se aplican límites de 60 000 bytes de entrada, 1600 tokens de salida, 200 000 bytes de respuesta y 120 segundos. Los costes son estimaciones, no facturación.

Tras revisión y autorización de plataforma, el smoke aislado preparado se invocaría con `powershell -File scripts/Run-Claude-Smoke.ps1 -Execute`. Sin `-Execute` no realiza acciones. No se ha ejecutado en esta preparación.


### Operación preparada para revisión de Central

Los siguientes comandos son artefactos preparados offline y no se han ejecutado en esta fase. Tras la revisión y autorización de plataforma, el smoke sintético se presenta con:

```powershell
powershell -File scripts/Run-Claude-Smoke.ps1 -Execute
```

El cambio de proveedor requiere el nombre exacto del manifiesto vigente, verificado por Central:

```powershell
powershell -File scripts/Switch-LocalProvider.ps1 -ExpectedRunName <currentverifiedfrommanifest> -Provider claude -Execute
```

El switch comprueba PID, ejecutable, hora de inicio, línea de comando y propietario del listener contra el manifiesto; el directorio de trabajo es el registrado por el launcher, no una lectura independiente del proceso Windows. Prepara copia SQLite coherente y código histórico de rollback antes de detener. El backup contiene datos privados y permanece bajo `.runtime`; nunca se restaura automáticamente sobre la base viva. Si no puede verificar un proceso o un lanzamiento no deja manifiesto, se detiene y requiere inspección. En manifiestos antiguos sin ASR, registra valores del entorno actual y defaults resueltos, no afirma conocer el entorno original. Los hashes de código son de archivos en disco al iniciar, no prueba independiente de bytes cargados en memoria.

M02 conserva un ledger fijo con máximo USD 0.50 y ocho llamadas; M04 usa otro ledger con máximo USD 1.50. Los resultados con coste incierto suspenden nuevas llamadas hasta revisión; no borrar ni reiniciar el ledger o lock. El coste M02 nuevo de esta fase fue USD 0. El smoke tiene límite de 250 segundos por request y 480 segundos totales.


El adaptador preparado para Claude Sonnet 5.5 envía `thinking: {"type":"between_tools"}`. M04 observó un 400 al enviar `disabled`; la [documentación oficial de Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5) indica el cambio. El fallo previo M02 no conservó su error HTTP, por lo que no se afirma retrospectivamente su status. La corrección aún requiere prueba real autorizada.


Una revisión operativa append-only puede vincular una reserva incierta a evidencia y al provider corregido. No cambia la entrada original, no determina facturación y mantiene la reserva completa y el número de llamadas dentro del límite. Un resultado nuevo incierto vuelve a bloquear la siguiente llamada. La revisión requiere hashes vigentes del ledger, evidencia y provider; ver `sessions/mesa-02/M02-CLAUDE-R3/HANDOFF.md`.


Si el servicio está detenido, Central puede revisar `powershell -File scripts/Start-StoppedLocalProvider.ps1 -Provider claude -Execute`. Sin `-Execute` es NOOP. El script exige el puerto 8765 libre y una base `app/data/companion.sqlite3` existente; prepara backup SQLite privado y metadatos agregados sin filas, luego llama al launcher. No detiene procesos ni restaura backups automáticamente. La disponibilidad y el resultado del arranque real requieren verificación operativa.

Manual device-check hosting requires a coordinator-frozen release, hashed viewer compatibility evidence and an independent live M04 browser check described in [the gateway contract](contracts/GATEWAY.md). No manual READY or usable invitation is claimed before those checks.
