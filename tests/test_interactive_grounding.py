"""Unit tests for interactive/grounding.py - ADR-0032's tiered
grounding model, built as real code (ticket #152). Every fixture is
hand-built JSON matching each document's own real schema shape, not a
live store - the interactive server has none."""
import json

from interactive.customization import DocumentRef, SiteOutput
from interactive.grounding import grounding_for

SITE = "example.com"


def _write(tmp_path, filename, extension, payload):
    content = json.dumps(payload) if not isinstance(payload, str) else payload
    (tmp_path / f"{SITE}_{filename}_20260101T000000Z.{extension}").write_text(content, encoding="utf-8")


def _where(tmp_path) -> SiteOutput:
    return SiteOutput(out_dir=str(tmp_path), site=SITE)


def test_tokens_grounding_finds_real_usa_token_citers(tmp_path):
    _write(tmp_path, "tokens", "json", {
        "core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}},
        "semantic": {},
    })
    _write(tmp_path, "export", "json", {
        "@context": "./export.context.jsonld", "run_id": "x",
        "@graph": [
            {"id": "core.color.surface-1", "type": "Token", "label": "core.color.surface-1"},
            {"id": "example.com/|button.buy", "type": "Componente", "usa_token": ["core.color.surface-1"]},
        ],
    })

    facts = grounding_for(_where(tmp_path), DocumentRef("tokens", "json"))

    assert len(facts) == 1
    assert "core.color.surface-1" in facts[0].statement
    assert "example.com/|button.buy" in facts[0].statement


def test_tokens_grounding_omits_a_token_no_component_cites(tmp_path):
    _write(tmp_path, "tokens", "json", {
        "core": {"color": {"unused": {"$type": "color", "$value": "#000"}}},
        "semantic": {},
    })
    _write(tmp_path, "export", "json", {"@graph": []})

    facts = grounding_for(_where(tmp_path), DocumentRef("tokens", "json"))

    assert facts == []


def test_tokens_grounding_is_empty_when_export_json_was_never_produced(tmp_path):
    _write(tmp_path, "tokens", "json", {"core": {}, "semantic": {}})

    assert grounding_for(_where(tmp_path), DocumentRef("tokens", "json")) == []


def test_catalog_grounding_reads_the_alias_already_in_the_file_directly(tmp_path):
    """No CatalogEntry/member_paths reconstruction needed - the alias is
    already literal in custom-elements.json's own serialized JSON."""
    _write(tmp_path, "custom-elements", "json", {
        "schemaVersion": "2.1.0", "readme": "",
        "modules": [{
            "kind": "javascript-module", "path": "observed/SubmitButton",
            "declarations": [{
                "kind": "class", "name": "SubmitButton",
                "x-tokens": {"color": ["{core.color.surface-1}"], "spacing": []},
            }],
            "exports": [],
        }],
    })

    facts = grounding_for(_where(tmp_path), DocumentRef("custom-elements", "json"))

    assert len(facts) == 1
    assert "SubmitButton" in facts[0].statement
    assert "core.color.surface-1" in facts[0].statement


def test_catalog_grounding_skips_a_declaration_with_no_color_tokens(tmp_path):
    _write(tmp_path, "custom-elements", "json", {
        "schemaVersion": "2.1.0", "readme": "",
        "modules": [{
            "kind": "javascript-module", "path": "observed/Plain",
            "declarations": [{"kind": "class", "name": "Plain", "x-tokens": {"color": [], "spacing": []}}],
            "exports": [],
        }],
    })

    assert grounding_for(_where(tmp_path), DocumentRef("custom-elements", "json")) == []


def test_risk_register_grounding_cites_the_real_service_name(tmp_path):
    _write(tmp_path, "risk-register", "json", [
        {"service": "payments-api", "rule": "information-disclosure", "description": "Discloses X-Powered-By."},
    ])

    facts = grounding_for(_where(tmp_path), DocumentRef("risk-register", "json"))

    assert len(facts) == 1
    assert "payments-api" in facts[0].statement
    assert "Discloses X-Powered-By." in facts[0].statement


def test_content_inventory_grounding_cites_component_ref_and_screens(tmp_path):
    _write(tmp_path, "content-inventory", "json", [
        {"component_ref": "LegalNotice#variant-1", "screens": ["SCR-a1b2c3"], "text": "Terms apply."},
    ])

    facts = grounding_for(_where(tmp_path), DocumentRef("content-inventory", "json"))

    assert len(facts) == 1
    assert "LegalNotice#variant-1" in facts[0].statement
    assert "SCR-a1b2c3" in facts[0].statement
    assert "Terms apply." in facts[0].statement


def test_grounding_for_an_unhandled_document_is_honestly_empty_not_fabricated(tmp_path):
    """Tier c - gherkin has no tier-a/b path in this first pass, and
    must say so plainly rather than guess."""
    _write(tmp_path, "gherkin", "feature", "Feature: whatever\n")

    assert grounding_for(_where(tmp_path), DocumentRef("gherkin", "feature")) == []
