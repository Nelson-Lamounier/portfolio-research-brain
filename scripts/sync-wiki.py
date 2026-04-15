#!/usr/bin/env python3
"""
sync-wiki.py — Sync wiki pages to S3 for two consumers:

  1. kb-docs/          → Bedrock Knowledge Base (original pages + .metadata.json sidecars)
  2. portfolio-docs/   → Portfolio-doc site (wikilinks transformed, portfolio frontmatter)

Usage:
  WIKI_S3_BUCKET=my-bucket python3 scripts/sync-wiki.py

Required env vars:
  WIKI_S3_BUCKET    S3 bucket name

Optional env vars:
  AWS_PROFILE       AWS CLI profile (falls back to default credential chain)
  DRY_RUN           Set to "1" to print actions without uploading
"""

import os
import re
import sys
import json
import boto3
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install -r scripts/requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).parent.parent
WIKI_DIR    = REPO_ROOT / "wiki"
INDEX_FILE  = REPO_ROOT / "index.md"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
S3_BUCKET       = os.environ.get("WIKI_S3_BUCKET", "")
KB_PREFIX       = "kb-docs"         # Bedrock KB source prefix
PORTFOLIO_PREFIX = "portfolio-docs"  # Portfolio-doc source prefix
DRY_RUN         = os.environ.get("DRY_RUN", "") == "1"

if not S3_BUCKET and not DRY_RUN:
    print("ERROR: WIKI_S3_BUCKET env var is required. Set DRY_RUN=1 to test without S3.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# S3 client
# ---------------------------------------------------------------------------
s3 = boto3.client("s3") if not DRY_RUN else None


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

def extract_frontmatter(content: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_raw = content[4:end].strip()
    body = content[end + 4:].strip()
    try:
        fm = yaml.safe_load(fm_raw)
        return (fm or {}), body
    except yaml.YAMLError:
        return {}, body


def build_portfolio_frontmatter(fm: dict, body: str) -> str:
    """
    Build Markdoc-compatible frontmatter for portfolio-doc.
    Keeps title, adds nextjs.metadata.description extracted from body.
    """
    title = fm.get("title", "Untitled")

    # Try ## Summary section first, then first non-heading paragraph
    description = ""
    summary_match = re.search(
        r'^## Summary\s*\n([\s\S]+?)(?=\n##|\Z)', body, re.MULTILINE
    )
    if summary_match:
        raw = summary_match.group(1).strip()
        description = re.sub(r'\s+', ' ', re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', raw))[:200]
    else:
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("```") and len(line) > 30:
                description = re.sub(r'\s+', ' ', line)[:200]
                break

    # Strip any remaining wikilinks from the description
    description = _WIKILINK_RE.sub(lambda m: m.group(1).split("/")[-1].split("|")[-1], description)

    portfolio_fm = {
        "title": title,
        "nextjs": {
            "metadata": {
                "title": title,
                "description": description,
            }
        }
    }
    return "---\n" + yaml.dump(portfolio_fm, default_flow_style=False, allow_unicode=True).rstrip() + "\n---\n\n"


# ---------------------------------------------------------------------------
# Wikilink transformer
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')

def path_to_slug(rel: str) -> str:
    """
    Convert a relative wiki path to a URL slug.
    Mirrors the JS pathToSlug() in fetch-wiki.mjs so local and CI agree.

      "tools/argocd.md"           → "tools-argocd"
      "ai-engineering/chatbot.md" → "ai-engineering-chatbot"
      "argocd.md"                 → "argocd"  (root-level, no subdirectory)
    """
    return re.sub(r'\.md$', '', rel).replace("/", "-").replace("\\", "-")


def transform_wikilinks(content: str) -> str:
    """
    Replace Obsidian wikilinks with Markdoc-compatible markdown links.

      [[tools/argocd]]          → [argocd](/docs/tools-argocd)
      [[argocd]]                → [argocd](/docs/argocd)
      [[tools/argocd|Argo CD]]  → [Argo CD](/docs/tools-argocd)
    """
    def _replace(match: re.Match) -> str:
        inner = match.group(1)
        if "|" in inner:
            target, display = inner.split("|", 1)
            target = target.strip()
            display = display.strip()
        else:
            target = inner.strip()
            display = target.split("/")[-1]   # basename as default label

        # Path-qualified → join with "-"; bare name → use as-is
        if "/" in target:
            slug = target.replace("/", "-")
        else:
            slug = target
        return f"[{display}](/docs/{slug})"

    return _WIKILINK_RE.sub(_replace, content)


# ---------------------------------------------------------------------------
# Bedrock metadata sidecar
# ---------------------------------------------------------------------------

def build_metadata_json(fm: dict, category: str) -> dict:
    """
    Build a Bedrock Knowledge Base .metadata.json sidecar.
    Bedrock uses this for metadata filtering on RetrieveCommand calls.
    """
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    return {
        "metadataAttributes": {
            "type":     {"value": {"stringValue": fm.get("type", "")},     "type": "STRING"},
            "title":    {"value": {"stringValue": fm.get("title", "")},    "type": "STRING"},
            "category": {"value": {"stringValue": category},               "type": "STRING"},
            "tags":     {"value": {"stringListValue": tags},               "type": "STRING_LIST"},
            "updated":  {"value": {"stringValue": str(fm.get("updated", ""))}, "type": "STRING"},
        }
    }


# ---------------------------------------------------------------------------
# Navigation manifest (from index.md)
# ---------------------------------------------------------------------------

_H2_RE   = re.compile(r'^## (.+)', re.MULTILINE)
_LINK_RE = re.compile(r'^- \[\[([^\]]+)\]\]\s*(?:—\s*(.+))?', re.MULTILINE)


def parse_navigation() -> list[dict]:
    """
    Parse index.md into a navigation manifest consumed by portfolio-doc.

    Returns a list of section objects:
      [{ "title": "Projects", "links": [{ "title": "...", "href": "...", "description": "..." }] }]
    """
    if not INDEX_FILE.exists():
        return []

    content = INDEX_FILE.read_text(encoding="utf-8")
    _, body = extract_frontmatter(content)

    sections: list[dict] = []
    # Split body on ## headings
    parts = re.split(r'^(## .+)$', body, flags=re.MULTILINE)

    current_title = None
    for part in parts:
        part = part.strip()
        if not part:
            continue
        h2 = re.match(r'^## (.+)$', part)
        if h2:
            current_title = h2.group(1).strip()
            sections.append({"title": current_title, "links": []})
            continue
        if current_title and sections:
            for link_match in _LINK_RE.finditer(part):
                target = link_match.group(1).strip()
                description = (link_match.group(2) or "").strip()
                # Path-based slug: [[tools/argocd]] → "tools-argocd"
                # mirrors path_to_slug() and fetch-wiki.mjs pathToSlug()
                slug = target.replace("/", "-")
                # Title uses basename only for readability in nav
                basename = target.split("/")[-1]
                display_title = " ".join(
                    w.capitalize() if w.lower() not in ("and", "or", "of", "the", "vs") else w
                    for w in basename.split("-")
                )
                sections[-1]["links"].append({
                    "title": display_title,
                    "href": f"/docs/{slug}",
                    "description": description,
                })

    return sections


# ---------------------------------------------------------------------------
# S3 upload helpers
# ---------------------------------------------------------------------------

def _upload(key: str, body: str, content_type: str = "text/plain; charset=utf-8"):
    if DRY_RUN:
        print(f"  [DRY] s3://{S3_BUCKET}/{key}")
        return
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType=content_type,
    )
    print(f"  ↑ s3://{S3_BUCKET}/{key}")


def _upload_json(key: str, data: dict):
    _upload(key, json.dumps(data, indent=2, ensure_ascii=False), "application/json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    wiki_pages = sorted(WIKI_DIR.rglob("*.md"))
    if not wiki_pages:
        print("No wiki pages found. Nothing to sync.")
        return

    print(f"Syncing {len(wiki_pages)} wiki pages → s3://{S3_BUCKET or '<DRY_RUN>'}/\n")

    stats = {"kb": 0, "portfolio": 0, "errors": 0}

    for page_path in wiki_pages:
        rel       = page_path.relative_to(WIKI_DIR)   # e.g. tools/argocd.md
        slug      = page_path.stem                     # e.g. argocd
        category  = page_path.parent.name              # e.g. tools
        raw       = page_path.read_text(encoding="utf-8")
        fm, body  = extract_frontmatter(raw)

        print(f"→ {rel}")

        try:
            # ── Bedrock KB: original page + metadata sidecar ──────────────
            kb_key = f"{KB_PREFIX}/{rel}"
            _upload(kb_key, raw, "text/markdown; charset=utf-8")
            _upload_json(f"{kb_key}.metadata.json", build_metadata_json(fm, category))
            stats["kb"] += 1

            # ── Portfolio-doc: transformed page (path-preserving key) ────────
            # Key mirrors wiki/ subdirectory: portfolio-docs/tools/argocd.md
            # fetch-wiki.mjs derives slug via pathToSlug(key) = "tools-argocd"
            transformed_body    = transform_wikilinks(body)
            portfolio_fm_str    = build_portfolio_frontmatter(fm, body)
            portfolio_content   = portfolio_fm_str + transformed_body
            portfolio_key       = f"{PORTFOLIO_PREFIX}/{rel}"
            _upload(portfolio_key, portfolio_content, "text/markdown; charset=utf-8")
            stats["portfolio"] += 1

        except Exception as exc:
            print(f"  ERROR processing {rel}: {exc}")
            stats["errors"] += 1

    # ── Navigation manifest ────────────────────────────────────────────────
    nav = parse_navigation()
    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "pageCount": stats["portfolio"],
        "sections": nav,
    }
    _upload_json(f"{PORTFOLIO_PREFIX}/manifest.json", manifest)

    print(f"\n✅  KB pages:        {stats['kb']}")
    print(f"✅  Portfolio pages: {stats['portfolio']}")
    if stats["errors"]:
        print(f"⚠️   Errors:          {stats['errors']}")


if __name__ == "__main__":
    main()
