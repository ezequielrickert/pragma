"""Unit tests for generators/asyncapi.py - the CH-<hash>/MSG-<hash> id
scheme and x-inference shape (docs/adr/0018), proven correct against
synthetic ChannelObservation/MessageObservation fixtures since no real
capture instrumentation exists to produce either yet."""
import pytest

from core.registry import DOCUMENT_REGISTRY
from generators.asyncapi import (
    AsyncAPIDocument,
    ChannelObservation,
    MessageObservation,
    build_asyncapi_document,
    channel_id,
    message_id,
)
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/asyncapi.schema.json"


def _channel(protocol="ws", host="shop.example", address="/ws/cart", **overrides):
    return ChannelObservation(protocol=protocol, host=host, address=address, **overrides)


def _message(channel_address="/ws/cart", name="CartUpdated", payload_shape='{"total": "number"}', **overrides):
    return MessageObservation(channel_address=channel_address, name=name, payload_shape=payload_shape, **overrides)


# --- channel_id / message_id ---

def test_channel_id_is_deterministic_across_two_calls():
    channel = _channel()

    assert channel_id(channel) == channel_id(channel)
    assert channel_id(channel).startswith("CH-")


def test_channel_id_differs_for_a_different_protocol():
    """A ws and an http channel at the identical host/address are
    genuinely different channels - the protocol is part of the identity."""
    ws = _channel(protocol="ws")
    http = _channel(protocol="http")

    assert channel_id(ws) != channel_id(http)


def test_channel_id_never_collides_with_ep_hash():
    """EP-<hash> (ADR-0013) is method+host+path_pattern - CH-<hash> is its
    own family member, never mistakable for one."""
    assert channel_id(_channel()).startswith("CH-")
    assert not channel_id(_channel()).startswith("EP-")


def test_message_id_is_deterministic_across_two_calls():
    message = _message()

    assert message_id(message) == message_id(message)
    assert message_id(message).startswith("MSG-")


def test_message_id_differs_for_the_same_name_on_a_different_channel():
    """The same message name can mean something different on two
    channels - the channel address is part of the identity."""
    on_cart = _message(channel_address="/ws/cart", name="Updated")
    on_orders = _message(channel_address="/ws/orders", name="Updated")

    assert message_id(on_cart) != message_id(on_orders)


# --- bindings (ADR-0018 point 4) ---

def test_a_websocket_channel_gets_the_real_ws_binding():
    from generators.asyncapi import _channel_bindings

    assert _channel_bindings(_channel(protocol="ws")) == {"ws": {}}


def test_an_sse_channel_gets_http_plus_the_sse_flag():
    from generators.asyncapi import _channel_bindings

    bindings = _channel_bindings(_channel(protocol="http", is_sse=True))

    assert bindings == {"http": {}, "x-sse-stream": True}


def test_a_long_polling_channel_gets_http_plus_the_long_polling_flag():
    from generators.asyncapi import _channel_bindings

    bindings = _channel_bindings(_channel(protocol="http", is_long_polling=True))

    assert bindings == {"http": {}, "x-long-polling": True}


def test_a_plain_http_channel_gets_neither_flag():
    from generators.asyncapi import _channel_bindings

    assert _channel_bindings(_channel(protocol="http")) == {"http": {}}


# --- x-inference (ADR-0018 point 2) ---

def test_inference_confidence_scales_with_observation_count():
    from generators.asyncapi import _message_inference

    low = _message_inference(_message(observation_count=1))
    high = _message_inference(_message(observation_count=5))

    assert low["confidence"]["payload_shape"] < high["confidence"]["payload_shape"]
    assert high["confidence"]["payload_shape"] == 1.0


def test_inference_derived_from_is_reserved_not_invented():
    from generators.asyncapi import _message_inference

    assert _message_inference(_message())["derived_from"] == []


# --- build_asyncapi_document ---

def test_a_channel_lists_only_its_own_messages():
    channels = [_channel(address="/ws/cart"), _channel(address="/ws/orders")]
    messages = [_message(channel_address="/ws/cart", name="CartUpdated")]

    document = build_asyncapi_document(channels, messages, "shop.example")

    cart_id = channel_id(channels[0])
    orders_id = channel_id(channels[1])
    assert len(document["channels"][cart_id]["messages"]) == 1
    assert document["channels"][orders_id]["messages"] == {}


def test_every_message_appears_once_in_components():
    channels = [_channel()]
    messages = [_message(name="A"), _message(name="B")]

    document = build_asyncapi_document(channels, messages, "shop.example")

    assert len(document["components"]["messages"]) == 2


def test_the_document_validates_against_its_own_schema():
    channels = [_channel(protocol="ws"), _channel(protocol="http", address="/poll", is_long_polling=True)]
    messages = [_message(), _message(channel_address="/poll", name="Poll")]

    document = build_asyncapi_document(channels, messages, "shop.example")

    validate_against_schema(document, _SCHEMA_PATH)


def test_an_empty_crawl_produces_a_structurally_valid_empty_document():
    document = build_asyncapi_document([], [], "shop.example")

    validate_against_schema(document, _SCHEMA_PATH)
    assert document["channels"] == {} and document["components"]["messages"] == {}


# --- the registered document (ADR-0018 point 3) ---

def test_asyncapi_is_registered_so_manifest_can_enumerate_it():
    assert "asyncapi" in DOCUMENT_REGISTRY.names()


def test_generate_raises_rather_than_returning_an_empty_document():
    """No partial document is worth reserving a field on (ADR-0018 point
    3) - unlike evidence-log's screenshot: kind, nothing here is real."""
    with pytest.raises(NotImplementedError):
        AsyncAPIDocument().generate(request=None)
