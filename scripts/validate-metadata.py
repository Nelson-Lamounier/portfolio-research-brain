#!/usr/bin/env python3
"""
validate-metadata.py — Pre-sync schema check for Bedrock KB metadata sidecars.

Bedrock Knowledge Base S3 metadata files must use flat key-value pairs:
  {"metadataAttributes": {"type": "concept", "tags": ["aws"]}}

The typed-wrapper format ({"value": {"stringValue": ...}, "type": "STRING"})
is only valid in RetrieveCommand filter expressions — Bedrock rejects it in
sidecar files with "metadata file is not in valid JSON format".

Exit 1 if any page would produce an invalid sidecar.
"""

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load sync-wiki.py (hyphenated name — can't use normal import)
# ---------------------------------------------------------------------------
SCRIPT = Path(__file__).parent / "sync-wiki.py"
spec   = importlib.util.spec_from_file_location("sync_wiki", SCRIPT)
mod    = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

build_metadata_json = mod.build_metadata_json
extract_frontmatter = mod.extract_frontmatter

# ---------------------------------------------------------------------------
# Validate every wiki page
# ---------------------------------------------------------------------------
WIKI_DIR = Path(__file__).parent.parent / "wiki"
errors: list[str] = []

for page in sorted(WIKI_DIR.rglob("*.md")):
    rel      = page.relative_to(WIKI_DIR)
    category = page.parent.name
    raw      = page.read_text(encoding="utf-8")
    fm, _    = extract_frontmatter(raw)
    meta     = build_metadata_json(fm, category)
    attrs    = meta.get("metadataAttributes", {})

    # Rule 1: no attribute value may be a dict (typed-wrapper format)
    bad = {k: v for k, v in attrs.items() if isinstance(v, dict)}
    if bad:
        errors.append(
            f"{rel}: typed-wrapper values detected (Bedrock rejects): "
            + ", ".join(f"{k}" for k in bad)
        )

    # Rule 2: tags must be a list
    tags = attrs.get("tags", [])
    if not isinstance(tags, list):
        errors.append(f"{rel}: 'tags' must be list, got {type(tags).__name__}")

    # Rule 3: required keys present
    for key in ("type", "title", "category"):
        if not attrs.get(key):
            errors.append(f"{rel}: missing or empty required attribute '{key}'")

page_count = len(list(WIKI_DIR.rglob("*.md")))

if errors:
    print(f"\n❌ Metadata schema validation failed ({len(errors)} error(s)):\n")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)

print(f"✅ Metadata schema valid for {page_count} pages.")
