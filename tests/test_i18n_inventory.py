"""Unit tests for generators/i18n_inventory.py - the ICU MessageFormat
catalog shape, real and tested against synthetic fixtures even though
no capture instrumentation populates it yet (docs/adr/0027)."""
import pytest

from core.registry import DOCUMENT_REGISTRY
from generators.i18n_inventory import I18nInventoryDocument, LocaleVariant, build_i18n_inventory
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/i18n-inventory.schema.json"


def _variant(message_key="Button#variant-1", locale="en", text="Buy now"):
    return LocaleVariant(message_key=message_key, locale=locale, translated_text=text)


# --- build_i18n_inventory ---

def test_one_variant_produces_one_message_key_with_one_locale():
    catalog = build_i18n_inventory([_variant()])

    assert catalog == {"Button#variant-1": {"en": "Buy now"}}


def test_two_locales_of_the_same_message_key_accumulate_not_overwrite():
    variants = [_variant(locale="en", text="Buy now"), _variant(locale="es", text="Comprar ahora")]

    catalog = build_i18n_inventory(variants)

    assert catalog["Button#variant-1"] == {"en": "Buy now", "es": "Comprar ahora"}


def test_a_glossary_term_reference_is_a_valid_message_key_too():
    """message_key cites either content-inventory's component_ref or
    glossary's TERM-<hash> (ADR-0027 point 2) - this module has no
    opinion on which, it just keys the catalog by whatever string it's
    given."""
    catalog = build_i18n_inventory([_variant(message_key="TERM-abc123", locale="es", text="Boletín")])

    assert catalog == {"TERM-abc123": {"es": "Boletín"}}


def test_an_empty_observation_set_produces_an_empty_catalog_not_an_error():
    assert build_i18n_inventory([]) == {}


def test_the_document_validates_against_its_own_schema():
    catalog = build_i18n_inventory([_variant(locale="en"), _variant(locale="es", text="Comprar ahora")])

    validate_against_schema(catalog, _SCHEMA_PATH)


def test_an_empty_catalog_is_still_structurally_valid():
    validate_against_schema(build_i18n_inventory([]), _SCHEMA_PATH)


# --- the registered document (ADR-0027 point 1) ---

def test_i18n_inventory_is_registered_so_manifest_can_enumerate_it():
    assert "i18n-inventory" in DOCUMENT_REGISTRY.names()


def test_generate_raises_rather_than_returning_an_empty_document():
    """No partial document is worth reserving a field on here either -
    the same posture asyncapi.json already established (ADR-0018)."""
    with pytest.raises(NotImplementedError):
        I18nInventoryDocument().generate(request=None)
