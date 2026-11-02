# Optional local EN/ES voice distribution

**Status: HOLD — do not execute setup or advertise a clean-checkout local-voice installation as ready.** The Python dependency lock is complete for Windows x64 / CPython3.12. Exact selected Spanish-weight provenance and the source/notices correspondence of the archived phonemizer data remain unresolved. The replacement installer refuses execution before creating directories, downloading, creating a venv or calling pip. Its ordinary invocation only reports the hold. No acknowledgement option grants rights or removes this hold.

Undertone remains **all rights reserved**. Third-party component licenses apply to those components; this record neither relicenses Undertone nor concludes that downloading an optional external component automatically changes Undertone's license. No runtime, model, phonemizer, credential, private venv or model archive is included in this distribution proposal.

## Exact supported target and lock

Keep the existing adapter identity: `sherpa-onnx-cpu`, runtime1.12.40, `en_US-ljspeech-medium`, `es_MX-claude-high`, and the adapter's existing model hashes. No migration to the newer2.x runtime, lexicon conversion, voice substitution or new inference is authorized by this work.

The two runtime distributions are the entire declared Python dependency closure:

| Distribution | Exact wheel | Published SHA256 |
|---|---|---|
| sherpa-onnx1.12.40 | `sherpa_onnx-1.12.40-cp312-cp312-win_amd64.whl` | `a98c08848433af34ba0c81015f4ec1290f627d8ceec3d6d9df3380082cac408f` |
| sherpa-onnx-core1.12.40 | `sherpa_onnx_core-1.12.40-py3-none-win_amd64.whl` | `506aa30d7af5e182cc90fcabe841d1abc842c195ec19dfd3cb9aec3562b9c1e0` |

Sources: [sherpa-onnx version metadata](https://pypi.org/pypi/sherpa-onnx/1.12.40/json), [core version metadata](https://pypi.org/pypi/sherpa-onnx-core/1.12.40/json). The selected wheel's PEP658 METADATA was fetched separately and checked against its published metadata digest. The wrapper requires only `sherpa-onnx-core==1.12.40`; core declares no `Requires-Dist`. Conversion-script build tools are not runtime dependencies. No wheel bytes were downloaded or locally hashed, and no install was performed.

`scripts/LOCAL_VOICE_WINDOWS_CP312.lock.txt` pins both exact public wheel URLs/hashes with CPython3.12/Windows/x64 markers, `--require-hashes`, `--only-binary=:all:` and `--no-index`. `LOCAL_VOICE_DEPENDENCY_LOCK.json` preserves the dependency graph, selected filenames, sizes and metadata digests. The manifest binds that JSON's SHA256; the JSON binds the requirements file's SHA256. A future released setup must preserve this chain and the explicit platform refusal: markers alone can silently select nothing on an unsupported machine.

Evaluator-provided CPython3.12 x64, its standard library and bundled `venv`/`ensurepip` are bootstrap prerequisites, outside the two-distribution runtime lock. This is an ABI/platform-specific wheel lock, not a claim of identical OS, Python patch, bundled pip, native build provenance or bit-reproducible binaries. Native linked libraries are addressed separately in the notices, not disguised as additional Python packages.

## Artifact facts and remaining external limits

Both historical archive hashes are now independently corroborated by GitHub's published asset metadata: [EN asset276487068](https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/assets/276487068), [ES asset324610087](https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/assets/324610087). This proves published digest agreement, not archive membership, license coverage or local download verification.

**EN:** the [voice trainer's LJSpeech medium entry](https://brycebeattie.com/files/tts/) explicitly declares the voice public domain. The [dataset owner](https://keithito.com/LJ-Speech-Dataset/) separately describes the corpus's public-domain status. The [converted repository at34f390d13b9edbaa30c339127de0f9c4c5948c90](https://huggingface.co/api/models/csukuangfj/vits-piper-en_US-ljspeech-medium/tree/34f390d13b9edbaa30c339127de0f9c4c5948c90) publishes LFS SHA256 `8ceba58a4b540d4e7e7e24ad079cf0d92762a4fd334e059f12940787c6c37b3d`, matching the required converted model. These are distinct evidence for the original voice, dataset and converted identity; they do not identify the archived eSpeak data's source revision.

**ES — external limit ES_EXACT_WEIGHT_TRACEABILITY:** the adapter requires SHA256 `6b7a54f5fcc8c9ce3788cd308a26cfa429ad025cdff4a7a6c34d025d0d229341`. The [converted repository at802b53b82c60d3de4f8b965314ac99bbec2499b0](https://huggingface.co/api/models/csukuangfj/vits-piper-es_MX-claude-high/tree/802b53b82c60d3de4f8b965314ac99bbec2499b0) instead publishes `f5eceb904655a60141037d957f21e6257efa93b8c8b7b818c0c57396217bcb1c`; the earlier weight-bearing revision has the same different hash. The [original HirCoir Space tree](https://huggingface.co/api/spaces/HirCoir/Piper-TTS-Spanish/tree/dd9664ff4143af8664c05c56765a2426a851a53a) has `es_MX-claude-14947-epoch-high.onnx` SHA256 `3ef40a71ea63852cd8ab7e6fa7d2ecdcfa67a0b47c9c48e3f10e02ee02083ea0`. Its Space README declares Apache2.0 and the Piper model card labels its **dataset** Apache2.0. Neither statement nor a different weight hash establishes the exact required converted artifact's provenance/terms. Do not change the adapter hash to make these match.

Needed external evidence: a publisher-controlled per-member manifest or equivalent conversion/source/terms record for the exact ES GitHub archive digest `ec33fb689c248fe64810aab564cba97babf0f506672cfd404928d46e751a4721`, explicitly binding required ONNX hash `6b7a54f5…` to its originating model revision and applicable grant/notices. The archive is public, not claimed inaccessible; this assignment excludes downloading its weights/container. Metadata examined does not supply that binding. No upstream contact, guessed grant or private installed model inspection was substituted.

**Both archives — external limit ESPEAK_ARCHIVE_SOURCE_AND_NOTICES:** the conversion recipe obtains an unversioned `espeak-ng-data.tar.bz2`. The public converted model repositories expose a compiled data tree but no source revision/license inventory for the data inside the two selected GitHub archives. The runtime source recipe pins a particular eSpeak fork commit; that is not proof it produced those archived data files. Needed: exact archived data inventory, originating source/build revision, applicable copyright/license notices and a corresponding-source delivery reference where required. Do not replace the data, rebuild voices, or declare the complete archive Apache-only.

## Integration and operation

The lock files and the sourced factual documentation/notices can be reviewed for the GitHub candidate now. `FILE_RELEASE.json` distinguishes those released additions from the **held** installer/manifest pair. Do not apply a full-file replacement to the shared adaptations document: merge only the supplied local-speech fragment, leaving owner17's hosted decisions intact.

The installer and manifest are a mutually consistent **held replacement proposal**, not an installable release. `python -B scripts/Install-LocalVoice.py` is a NOOP; `--execute` currently refuses with the two exact findings before effects. A later owner must add actual missing publisher evidence, retain applicable terms/source obligations, and review the concrete release delta before changing the hold. Flipping `ready`, deleting findings or supplying a human acknowledgement alone is not evidence.

After that substantive release, installation would remain a separate explicit evaluator action with an existing supported interpreter and a new project-relative target. Existing installations are refused; no merge or deletion is supplied. The retained implementation verifies the archive hash and required model hash, preserves the already reviewed bounded extraction/path guards, creates its own venv and consumes only the hash-bound wheel lock. Those17 prior synthetic checks are reused, not rerun here; no clean installation, inference, hearing or availability claim follows this metadata work. This work does not remove hosted invoice/grant/privacy/budget holds or close Waves17/21.
