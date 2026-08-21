"""Every `Details:` pointer in the source resolves to a real doc and a real
heading, and every doc describes a module that still exists.

Why this is a test rather than a review habit: the storage migration left 19
pointers aimed at files that were never written and 2 docs describing deleted
modules, and nobody noticed because a dangling pointer costs nothing until
someone follows it. `docs/dev/README.md` states the rule ("a stale `Details:`
pointer or a doc section describing behavior the code no longer has is worse
than no doc at all"); this is the rule with teeth.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_DOCS = ROOT / "docs" / "dev"

# Top-level packages docs/dev mirrors, per its own README.
_DOCUMENTED_PACKAGES = ("core", "agents", "dashboard", "database", "spiders", "generators", "utils", "analysis")

_POINTER = re.compile(r"docs/dev/([A-Za-z0-9_./-]*\.md)(?:#([A-Za-z0-9_-]+))?")


def _python_sources():
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if "__pycache__" in parts or ".claude" in parts or parts[0] == "tests":
            continue
        yield path


def _heading_slugs(doc: Path):
    """GitHub's own anchor rule, as far as this project's headings exercise it:
    lowercase, punctuation dropped, spaces to hyphens - underscores and
    hyphens survive."""
    text = doc.read_text(encoding="utf-8")
    return {
        re.sub(r"[^a-z0-9 _-]", "", heading.strip().lower()).replace(" ", "-")
        for heading in re.findall(r"^#+\s+(.*)$", text, re.M)
    }


def test_every_details_pointer_resolves():
    """A pointer naming a file that does not exist, or a heading that does not
    exist in it, sends a reader nowhere."""
    broken = []
    for source in _python_sources():
        for doc_name, anchor in _POINTER.findall(source.read_text(encoding="utf-8", errors="ignore")):
            doc = DEV_DOCS / doc_name
            if not doc.exists():
                broken.append(f"{source.relative_to(ROOT)} -> {doc_name} (no such file)")
            elif anchor and anchor.lower() not in _heading_slugs(doc):
                broken.append(f"{source.relative_to(ROOT)} -> {doc_name}#{anchor} (no such heading)")

    assert not broken, "dangling Details: pointers:\n" + "\n".join(f"  {entry}" for entry in sorted(set(broken)))


def test_every_dev_doc_describes_a_module_that_exists():
    """The other direction: a doc left behind by a deleted module reads as
    current documentation for code that is gone."""
    orphans = []
    for doc in DEV_DOCS.rglob("*.md"):
        relative = doc.relative_to(DEV_DOCS)
        if relative.name == "README.md":
            continue
        if relative.parts[0] not in _DOCUMENTED_PACKAGES and len(relative.parts) > 1:
            continue
        source = ROOT / relative.with_suffix(".py")
        if not source.exists():
            orphans.append(str(relative))

    assert not orphans, "docs for modules that no longer exist:\n" + "\n".join(
        f"  docs/dev/{entry}" for entry in sorted(orphans)
    )
