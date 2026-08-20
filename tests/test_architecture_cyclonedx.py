"""Unit tests for generators/architecture_cyclonedx.py - pure functions
over GraphStore.integrations()' own row shape, no store needed."""
from generators.architecture_cyclonedx import build_cyclonedx_document, hosts_by_traffic


def _row(host, call_count=1):
    return {"host": host, "method": "GET", "path_pattern": "/x", "call_count": call_count}


def test_endpoints_are_grouped_into_one_service_per_host():
    integrations = [_row("cdn.example.com", 5), _row("cdn.example.com", 3)]

    hosts = hosts_by_traffic(integrations)

    assert hosts == [("cdn.example.com", 8, 2)]


def test_busiest_host_comes_first():
    integrations = [_row("quiet.example.com", 1), _row("busy.example.com", 100)]

    hosts = hosts_by_traffic(integrations)

    assert hosts[0][0] == "busy.example.com"


def test_the_document_validates_as_a_minimal_cyclonedx_bom():
    document = build_cyclonedx_document([_row("cdn.example.com", 5)])

    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.6"
    assert len(document["externalServices"]) == 1


def test_evidence_properties_carry_the_real_observation_count():
    document = build_cyclonedx_document([_row("cdn.example.com", 5), _row("cdn.example.com", 3)])

    properties = {p["name"]: p["value"] for p in document["externalServices"][0]["properties"]}
    assert properties["pragma:evidence:observationCount"] == "8"
    assert properties["pragma:evidence:source"] == "network-traffic-analysis"


def test_har_request_id_is_reserved_not_invented():
    document = build_cyclonedx_document([_row("cdn.example.com")])

    properties = {p["name"]: p["value"] for p in document["externalServices"][0]["properties"]}
    assert properties["pragma:evidence:harRequestId"] == ""


def test_no_third_party_traffic_is_an_empty_services_list_not_an_error():
    document = build_cyclonedx_document([])

    assert document["externalServices"] == []
