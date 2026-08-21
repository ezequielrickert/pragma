"""Unit tests for dashboard/redoc_renderer.py - Redoc integration for
openapi.yaml (ADR-0016 point 2, ticket #124).

Verified against a real openapi.yaml built by generators/openapi.py's
own real functions, not a hand-typed fixture - the ticket's own "Done
when" asks for a real fixture. Opening the result in an actual browser
to confirm Redoc renders visually isn't something this environment can
do; the strongest available proxy is confirming the embedded spec is
byte-for-byte the same document the real generator produced, and that
the page is well-formed HTML referencing Redoc's own real CDN bundle."""
import json

import yaml
import pytest

from core.documents import ProducedDocument
from core.interfaces import InferredRequest
from dashboard.redoc_renderer import render_redoc_page

openapi_spec_validator = pytest.importorskip("openapi_spec_validator")

from generators.openapi import build_openapi_document  # noqa: E402


def _document():
    return ProducedDocument(
        name="openapi", title="API Contract", purpose="Every endpoint the crawl observed, as an OpenAPI 3.1 spec.",
        path="/out/x_openapi_1.yaml", kind="source", checksum="a" * 64, filename="openapi",
        relative_link="x_openapi_1.yaml",
    )


def _real_openapi_yaml():
    request = InferredRequest(
        method="GET", endpoint="shop.example/api/orders", query_params=(), body_shape="",
        response_shape=json.dumps({"id": "string"}), triggered_by=(), loaded_by=(), status_codes=(200,),
    )
    spec = build_openapi_document([request], "shop.example")
    return spec, yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)


def test_the_embedded_spec_is_byte_identical_to_the_real_generator_output():
    spec, content = _real_openapi_yaml()

    html = render_redoc_page(_document(), content)

    embedded = html.split('id="spec-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == spec


def test_the_page_references_redocs_own_cdn_bundle():
    _, content = _real_openapi_yaml()

    html = render_redoc_page(_document(), content)

    assert "cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js" in html


def test_redoc_init_is_called_with_the_container_element():
    _, content = _real_openapi_yaml()

    html = render_redoc_page(_document(), content)

    assert "Redoc.init(" in html
    assert 'id="redoc-container"' in html


def test_title_and_purpose_are_rendered_and_escaped():
    document = ProducedDocument(
        name="openapi", title="API <Contract>", purpose="Spec & docs.", path="/out/x.yaml",
        kind="source", checksum="a" * 64, filename="openapi", relative_link="x.yaml",
    )
    _, content = _real_openapi_yaml()

    html = render_redoc_page(document, content)

    assert "API <Contract>" not in html
    assert "&lt;Contract&gt;" in html
    assert "Spec &amp; docs." in html


def test_the_page_is_well_formed_self_contained_html_apart_from_the_one_cdn_script():
    _, content = _real_openapi_yaml()

    html = render_redoc_page(_document(), content)

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    # The one intentional external reference is Redoc's own CDN bundle -
    # no other http(s) URL should appear anywhere on the page.
    other_urls = [line for line in html.splitlines() if "http" in line and "redoc.standalone.js" not in line]
    assert other_urls == []
