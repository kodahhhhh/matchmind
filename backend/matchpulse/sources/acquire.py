"""Small openly licensed archive acquisition through the shared polite cache."""

import argparse
import hashlib
import shutil
import stat
import zipfile
from pathlib import Path

from matchpulse.config import get_settings
from matchpulse.sources.common import save_json
from matchpulse.sources.fetch import PublicFetcher


def extract_archive(archive: Path, root: Path) -> int:
    """Extract match/event files; reject unsafe paths and oversized archives."""
    root.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if sum(m.file_size for m in members) > 1024**3:
            raise ValueError("Archive exceeds the 1 GB extraction budget")
        for member in members:
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Archive symlinks are prohibited")
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root.resolve()):
                raise ValueError("Unsafe archive path")
            if member.filename.endswith(("/match.json", "/events.jsonl")):
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(member))
                count += 1
    return count


def dynasty(data_dir: Path) -> dict:
    """Fetch immutable cached public ZIP and attribution/licence documentation."""
    if shutil.disk_usage(data_dir).free < 2 * 1024**3:
        raise ValueError("Less than 2 GB free; declining archive download")
    fetcher = PublicFetcher(data_dir)
    base = "https://raw.githubusercontent.com/Afriskaut/dynasty-scouting-league-2024-open-data/main/"
    for name in (
        "README.md",
        "LICENSE",
        "Afriskaut%20Event%20Map%20-%202024.pdf",
        "Pitch%20Coordinates%20For%20Afriskaut%20Event%20Data.pdf",
    ):
        fetcher.fetch("dynasty", base + name)
    archive = fetcher.fetch("dynasty", base + "Datasets.zip")
    report = {
        "archive_path": str(archive),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "licence": "Apache-2.0",
        "newly_extracted_files": extract_archive(
            archive, data_dir / "raw/dynasty/extracted"
        ),
    }
    save_json(data_dir / "sources/dynasty_manifest.json", report)
    return report


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(dynasty(get_settings().data_dir))


if __name__ == "__main__":
    main()
