"""Explicit setup only; downloads the pinned MIT model and verifies every file hash."""
import hashlib, json, os
from pathlib import Path
from huggingface_hub import snapshot_download

APP = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((Path(__file__).parent / "ASR_MODEL_MANIFEST.json").read_text(encoding="utf-8"))
CACHE = APP / ".runtime" / "huggingface"
os.environ.update(HF_HOME=str(CACHE), HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
                  HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_OFFLINE="0")
root = Path(snapshot_download(repo_id=MANIFEST["repo"], revision=MANIFEST["revision"],
    cache_dir=str(CACHE / "hub"), token=False,
    allow_patterns=[x["name"] for x in MANIFEST["files"]]))
for item in MANIFEST["files"]:
    path = root / item["name"]
    if not path.is_file() or path.stat().st_size != item["size"]:
        raise SystemExit(f"File size mismatch: {item['name']}")
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if digest != item["sha256"]:
        raise SystemExit(f"SHA-256 mismatch: {item['name']}")
print(json.dumps({"model_path": str(root), "repo": MANIFEST["repo"],
                  "revision": MANIFEST["revision"], "license": MANIFEST["license"]}))
