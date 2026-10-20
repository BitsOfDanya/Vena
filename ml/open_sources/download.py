"""Official sources only; resumable by completed file, atomic writes, provenance."""

import argparse
import hashlib
import json
import shutil
import stat
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "metropt3": {
        "page": "https://archive.ics.uci.edu/dataset/791/metropt+3+dataset",
        "license": "CC BY 4.0",
        "citation": "Davari et al. (2021), DOI 10.24432/C5VW3R",
        "files": {
            "source.zip": {
                "url": "https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip",
            },
        },
    },
    "hydraulic": {
        "page": "https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems",
        "license": "CC BY 4.0",
        "citation": "Helwig, Pignanelli & Schuetze (2015), DOI 10.24432/C5CW21",
        "files": {
            "source.zip": {
                "url": "https://archive.ics.uci.edu/static/public/447/condition%2Bmonitoring%2Bof%2Bhydraulic%2Bsystems.zip",
            },
        },
    },
    "water": {
        "page": "https://zenodo.org/records/15096167",
        "license": "CC BY 4.0 (dataset README)",
        "citation": "Babela, Munk & Munkova (2025), DOI 10.5281/zenodo.15096167",
        "files": {
            "water.csv": {
                "url": "https://zenodo.org/records/15096167/files/input_model_potenc_predXfault7_A.csv?download=1",
                "md5": "ae08cf142a6128f9ddc205a2ccbf80a9",
            },
            "README.txt": {
                "url": "https://zenodo.org/records/15096167/files/README.txt?download=1",
                "md5": "850d7486a5ad81d87021b6e162e17a19",
            },
        },
    },
    "nist_smoke": {
        "page": "https://www.nist.gov/el/fire/engineered-fire-safety/data-smoke-alarm-performance",
        "license": "Public NIST experimental data; retain attribution and source terms",
        "citation": "NIST TN 1947, smoke alarm performance experiments",
        "files": {
            "smoke_box.zip": {"url": "https://www.nist.gov/document/smokeboxdatazip"},
            "room.zip": {"url": "https://www.nist.gov/document/roomdatazip"},
        },
    },
}


def digest(path, algorithm="sha256"):
    result = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def safe_extract(archive_path, destination):
    destination = Path(destination)
    with zipfile.ZipFile(archive_path) as archive:
        # Known datasets are smaller than this when expanded.
        if sum(m.file_size for m in archive.infolist()) > 2_000_000_000:
            raise ValueError("Archive exceeds extraction size limit")
        for member in archive.infolist():
            path = PurePosixPath(member.filename.replace("\\", "/"))
            mode = member.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode):
                raise ValueError(f"Unsafe archive entry: {member.filename}")
            target = destination.joinpath(*path.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError(
                    f"Archive entry escapes destination: {member.filename}"
                )
        # Validate before mutating any extracted files.
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupted archive entry: {bad}")
        archive.extractall(destination)


def fetch_file(url, path, expected_md5=None, force=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or force:
        partial = path.with_suffix(path.suffix + ".part")
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "VENA-public-data-research/1.0"}
                )
                with (
                    urllib.request.urlopen(request, timeout=90) as response,
                    partial.open("wb") as dst,
                ):
                    if "text/html" in response.headers.get("Content-Type", ""):
                        raise ValueError(f"Expected data, received HTML from {url}")
                    shutil.copyfileobj(response, dst, length=1024 * 1024)
                if not partial.stat().st_size:
                    raise ValueError("Empty download")
                if expected_md5 and digest(partial, "md5") != expected_md5:
                    raise ValueError("Published MD5 mismatch")
                if path.suffix == ".zip":
                    with zipfile.ZipFile(partial) as archive:
                        if archive.testzip():
                            raise ValueError("Corrupt ZIP")
                partial.replace(path)
                break
            except (OSError, ValueError, zipfile.BadZipFile):
                partial.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    if expected_md5 and digest(path, "md5") != expected_md5:
        raise ValueError(
            f"Cached file differs from published MD5: {path}; use --force to replace"
        )
    return {
        "filename": path.name,
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def download_dataset(name, root, force=False):
    spec = SOURCES[name]
    directory = Path(root) / name
    manifest_path = directory / "download_manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous_hashes = {f["filename"]: f["sha256"] for f in previous.get("files", [])}
    entries = []
    for filename, source in spec["files"].items():
        path = directory / filename
        if (
            not force
            and path.exists()
            and filename in previous_hashes
            and digest(path) != previous_hashes[filename]
        ):
            raise ValueError(f"Cached checksum changed: {path}")
        print(f"{name}: {filename}", flush=True)
        entry = fetch_file(source["url"], path, source.get("md5"), force)
        entries.append(entry)
        if path.suffix == ".zip":
            safe_extract(
                path, directory / ("raw" if filename == "source.zip" else path.stem)
            )
    manifest = {
        "dataset": name,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_page": spec["page"],
        "license": spec["license"],
        "citation": spec["citation"],
        "files": entries,
        "extracted_files": [
            {
                "path": str(p.relative_to(directory)),
                "bytes": p.stat().st_size,
                "sha256": digest(p),
            }
            for p in sorted(directory.rglob("*"))
            if p.is_file() and p.name not in {*spec["files"], "download_manifest.json"}
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", choices=SOURCES, default=list(SOURCES))
    parser.add_argument("--root", type=Path, default=ROOT / "external_datasets")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace cached files from official sources",
    )
    args = parser.parse_args()
    for name in args.datasets:
        result = download_dataset(name, args.root, args.force)
        print(f"{name}: verified {len(result['files'])} downloads", flush=True)


if __name__ == "__main__":
    main()
