"""Unit tests for interactive/token_form.py - the color-picker form's
own read/write logic (ticket #154), independent of the Flask route
that will call it."""
import json

from interactive.customization import DocumentRef, SiteOutput, effective_content
from interactive.token_form import color_tokens, save_color_tokens

SITE = "example.com"


def _where(tmp_path) -> SiteOutput:
    return SiteOutput(out_dir=str(tmp_path), site=SITE)


def _write_tokens(tmp_path, core_color):
    payload = {"core": {"color": core_color}, "semantic": {}}
    (tmp_path / f"{SITE}_tokens_20260101T000000Z.json").write_text(json.dumps(payload), encoding="utf-8")


def test_color_tokens_reads_every_core_color_value(tmp_path):
    _write_tokens(tmp_path, {
        "surface-1": {"$type": "color", "$value": "#2d7737"},
        "text-1": {"$type": "color", "$value": "#111111"},
    })

    tokens = color_tokens(_where(tmp_path))

    assert tokens == {"core.color.surface-1": "#2d7737", "core.color.text-1": "#111111"}


def test_color_tokens_is_empty_when_tokens_json_was_never_produced(tmp_path):
    assert color_tokens(_where(tmp_path)) == {}


def test_color_tokens_reads_the_customized_copy_when_one_exists(tmp_path):
    """ADR-0031's own read-time-resolution rule, exercised through this
    module rather than customization.py directly."""
    _write_tokens(tmp_path, {"surface-1": {"$type": "color", "$value": "#2d7737"}})
    save_color_tokens(_where(tmp_path), {"core.color.surface-1": "#0000ff"})

    assert color_tokens(_where(tmp_path)) == {"core.color.surface-1": "#0000ff"}


def test_save_color_tokens_patches_only_the_given_token(tmp_path):
    _write_tokens(tmp_path, {
        "surface-1": {"$type": "color", "$value": "#2d7737"},
        "text-1": {"$type": "color", "$value": "#111111"},
    })

    save_color_tokens(_where(tmp_path), {"core.color.surface-1": "#0000ff"})

    assert color_tokens(_where(tmp_path)) == {"core.color.surface-1": "#0000ff", "core.color.text-1": "#111111"}


def test_save_color_tokens_writes_a_schema_valid_document(tmp_path):
    """The write path is the real save_customized - a broken document
    would raise here exactly like it does for the raw-text editor."""
    _write_tokens(tmp_path, {"surface-1": {"$type": "color", "$value": "#2d7737"}})

    save_color_tokens(_where(tmp_path), {"core.color.surface-1": "#0000ff"})

    written = effective_content(_where(tmp_path), DocumentRef("tokens", "json"))
    parsed = json.loads(written)
    assert parsed["core"]["color"]["surface-1"]["$value"] == "#0000ff"
    assert parsed["core"]["color"]["surface-1"]["$type"] == "color"


def test_save_color_tokens_ignores_an_id_that_does_not_exist(tmp_path):
    """A stale form submission (the document changed between page load
    and save) must not crash or invent a new token."""
    _write_tokens(tmp_path, {"surface-1": {"$type": "color", "$value": "#2d7737"}})

    save_color_tokens(_where(tmp_path), {"core.color.removed-token": "#000000"})

    assert color_tokens(_where(tmp_path)) == {"core.color.surface-1": "#2d7737"}
