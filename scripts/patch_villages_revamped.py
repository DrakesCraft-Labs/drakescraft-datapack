"""Repair invalid swamp jigsaw pool namespaces in Villages Revamped archives."""

from __future__ import annotations

import argparse
import gzip
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import nbtlib


REPLACEMENTS = {
    "minecraft:village/swamp/decor": "brutos:village/swamp/decor",
    "minecraft:village/swamp/streets": "brutos:village/swamp/streets",
}
EXPECTED_CHANGES = 6


def replace_pools(value: object) -> int:
    """Replace only the known broken jigsaw pool values in an NBT tree."""
    changed = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "pool" and str(child) in REPLACEMENTS:
                value[key] = nbtlib.String(REPLACEMENTS[str(child)])
                changed += 1
            else:
                changed += replace_pools(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            changed += replace_pools(child)
    return changed


def patch_archive(source_path: Path, output_path: Path) -> int:
    """Write a verified patched copy while preserving all archive entries."""
    total = 0
    try:
        with ZipFile(source_path, "r") as source, ZipFile(
            output_path, "w", ZIP_DEFLATED
        ) as output:
            for entry in source.infolist():
                payload = source.read(entry)
                if entry.filename.endswith(".nbt"):
                    nbt = nbtlib.File.parse(BytesIO(gzip.decompress(payload)))
                    changed = replace_pools(nbt)
                    if changed:
                        raw = BytesIO()
                        nbt.write(raw)
                        payload = gzip.compress(raw.getvalue(), mtime=0)
                        total += changed
                        print(f"[FIX] {entry.filename}: {changed}")
                output.writestr(entry, payload)
    except (OSError, ValueError, gzip.BadGzipFile) as error:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"Could not patch {source_path}: {error}") from error

    if total != EXPECTED_CHANGES:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Expected {EXPECTED_CHANGES} corrections, found {total}; "
            "the upstream archive may have changed"
        )

    with ZipFile(output_path, "r") as verification:
        broken_entries = []
        for entry in verification.infolist():
            if not entry.filename.endswith(".nbt"):
                continue
            raw = gzip.decompress(verification.read(entry))
            if any(old.encode() in raw for old in REPLACEMENTS):
                broken_entries.append(entry.filename)
        corrupt_entry = verification.testzip()

    if broken_entries or corrupt_entry:
        output_path.unlink(missing_ok=True)
        detail = broken_entries or [corrupt_entry]
        raise RuntimeError(f"Patched archive failed verification: {detail}")
    return total


def main() -> int:
    """Parse command-line paths and patch one Villages Revamped archive."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original Villages Revamped ZIP")
    parser.add_argument("output", type=Path, help="destination for the patched ZIP")
    args = parser.parse_args()

    if args.source.resolve() == args.output.resolve():
        parser.error("source and output must be different files")
    if not args.source.is_file():
        parser.error(f"source archive does not exist: {args.source}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    total = patch_archive(args.source, args.output)
    print(f"[SUCCESS] Corrected {total} jigsaw pools: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"[ERROR] {error}")
        raise SystemExit(1) from error
