"""Prepare only public website files; never upload repository metadata or tools."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_site"
DIRECTORIES = {"assets", "blog", "productos", "privacidad"}
FILES = {
    "index.html", "styles.css", "app.js", "404.html", "robots.txt", "sitemap.xml",
    "staticwebapp.config.json", "analytics.js", "analytics-config.js", "analytics.css",
    "landing.css", "landing.js",
}
ALLOWED = {".html", ".css", ".js", ".json", ".xml", ".txt", ".svg", ".png",
           ".jpg", ".jpeg", ".webp", ".woff", ".woff2", ".ttf", ".ico"}


def build():
    if OUTPUT.exists():
        if OUTPUT.is_symlink() or OUTPUT.resolve().parent != ROOT.resolve():
            raise RuntimeError("Output must remain directly inside this repository")
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    selected = [ROOT / name for name in FILES if (ROOT / name).is_file()]
    for name in DIRECTORIES:
        folder = ROOT / name
        if folder.is_dir():
            selected.extend(path for path in folder.rglob("*") if path.is_file())
    total = 0
    digests = {}
    for path in sorted(selected):
        relative = path.relative_to(ROOT)
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError(f"Unexpected symlink: {relative}")
        if path.suffix.lower() not in ALLOWED or any(part.startswith('.') for part in relative.parts):
            raise RuntimeError(f"Unexpected file in public directories: {relative}")
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        data = target.read_bytes()
        total += len(data)
        digests[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    for required in ("index.html", "assets/products.js", "styles.css", "staticwebapp.config.json"):
        if not (OUTPUT / required).is_file():
            raise RuntimeError(f"Missing public file: {required}")
    if total >= 250 * 1024 * 1024:
        raise RuntimeError("Public files exceed the Free environment storage limit")
    release = {"commit": os.environ.get("GITHUB_SHA", "local-check"),
               "builtAt": datetime.now(timezone.utc).isoformat(),
               "files": len(digests), "bytes": total,
               "contentHash": hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()}
    (OUTPUT / "version.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(release))


if __name__ == "__main__":
    build()
