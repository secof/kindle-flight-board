#!/usr/bin/env python3
"""
Airline Logo Downloader & Alias Linker Script

Reads logos.json mapping airline codes to image URLs, downloads each logo,
and automatically generates alias files/links based on aliases.json (e.g. W6 -> W4, W9, WZZ, WMT, WUK).
"""

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

FALLBACK_CDN_TEMPLATE = "https://images.kiwi.com/airlines/128/{code}.png"


def get_file_extension(url: str) -> str:
    """Extract file extension from URL or default to .png."""
    path = url.split("?")[0].split("#")[0]
    ext = os.path.splitext(path)[1]
    return ext if ext else ".png"


def fetch_url(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()


def link_aliases(output_dir: Path, aliases_file: Path, overwrite: bool = False) -> int:
    """Create file copies/links for alias codes (e.g. W6 -> W4, W9, WZZ, WMT)."""
    if not aliases_file.exists():
        print(f"[*] Aliases file '{aliases_file}' not found. Skipping alias generation.")
        return 0

    with open(aliases_file, "r", encoding="utf-8") as f:
        try:
            aliases_map = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[!] Error parsing aliases file: {e}", file=sys.stderr)
            return 0

    linked_count = 0
    for primary_code, alias_list in aliases_map.items():
        primary_file = output_dir / f"{primary_code}.png"
        
        # If primary file doesn't exist, check if any alias file exists to use as primary
        if not primary_file.exists():
            for alt_code in alias_list:
                alt_file = output_dir / f"{alt_code}.png"
                if alt_file.exists():
                    primary_file = alt_file
                    break

        if not primary_file.exists():
            continue

        for alias in alias_list:
            if alias == primary_code:
                continue
            alias_file = output_dir / f"{alias}.png"

            if alias_file.exists() and not overwrite:
                continue

            try:
                shutil.copyfile(primary_file, alias_file)
                print(f"[🔗] Linked alias: {alias}.png -> {primary_file.name}")
                linked_count += 1
            except Exception as e:
                print(f"[!] Failed to link {alias}.png -> {primary_file.name}: {e}", file=sys.stderr)

    return linked_count


def download_logos(
    json_file: Path,
    output_dir: Path,
    aliases_file: Path,
    overwrite: bool = False,
    use_fallback: bool = True,
) -> None:
    if not json_file.exists():
        print(f"Error: JSON file '{json_file}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(json_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from '{json_file}': {e}", file=sys.stderr)
            sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(data)
    downloaded = 0
    skipped = 0
    failed = 0

    print(f"Starting download of {total} logos into '{output_dir.resolve()}'...\n")

    headers = {"User-Agent": DEFAULT_USER_AGENT}

    for code, url in data.items():
        ext = get_file_extension(url)
        filename = f"{code}{ext}"
        filepath = output_dir / filename

        if filepath.exists() and not overwrite:
            print(f"[-] {code} -> {filename} already exists. Skipping.")
            skipped += 1
            continue

        img_data = None
        source_url = url

        try:
            img_data = fetch_url(url, headers)
            print(f"[+] {code} -> Downloaded from {url}")
        except Exception as e:
            print(f"[!] {code} -> Primary URL failed ({e}).", file=sys.stderr)
            if use_fallback:
                fallback_url = FALLBACK_CDN_TEMPLATE.format(code=code)
                try:
                    img_data = fetch_url(fallback_url, headers)
                    source_url = fallback_url
                    print(f"[+] {code} -> Downloaded from fallback: {fallback_url}")
                except Exception as fb_err:
                    print(f"[!] {code} -> Fallback URL also failed ({fb_err}).", file=sys.stderr)

        if img_data:
            with open(filepath, "wb") as out_file:
                out_file.write(img_data)
            downloaded += 1
        else:
            failed += 1

    linked = link_aliases(output_dir, aliases_file, overwrite)

    print("\n--- Download & Link Summary ---")
    print(f"Total Logos:   {total}")
    print(f"Downloaded:    {downloaded}")
    print(f"Skipped:       {skipped}")
    print(f"Failed:        {failed}")
    print(f"Aliases Linked: {linked}")


def main():
    script_dir = Path(__file__).parent.resolve()

    parser = argparse.ArgumentParser(
        description="Download airline logo images from a JSON mapping file and create alias links."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=script_dir / "logos.json",
        help="Path to JSON file containing code: url mapping (default: logos.json in script dir)",
    )
    parser.add_argument(
        "-a",
        "--aliases",
        type=Path,
        default=script_dir / "aliases.json",
        help="Path to JSON file containing canonical: [aliases] mapping (default: aliases.json in script dir)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=script_dir,
        help="Output directory to save downloaded logos (default: script dir)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing logo files",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable automatic fallback to Kiwi CDN if primary URL fails",
    )

    args = parser.parse_args()
    download_logos(
        json_file=args.input,
        output_dir=args.output,
        aliases_file=args.aliases,
        overwrite=args.overwrite,
        use_fallback=not args.no_fallback,
    )


if __name__ == "__main__":
    main()
