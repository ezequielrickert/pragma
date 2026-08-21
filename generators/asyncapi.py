"""`asyncapi.json` - locked ready for WS/SSE/long-polling traffic no
instrumentation observes yet, docs/adr/0018.

**Entirely absent today, on purpose.** Zero capture instrumentation for
WebSockets, SSE, or long-polling exists in this crawl - not one kind
among several the way `evidence-log`'s `screenshot:` is reserved
(ADR-0017), but nothing real for any of it. `AsyncAPIDocument.generate`
raises rather than returning an empty-but-valid document: ADR-0018 point
3 is explicit that there is no partial document worth reserving a field
on, only real work to do once detection instrumentation exists as its
own future effort. `run_document_pipeline`'s existing "a generator that
fails is logged and skipped" degradation is what turns that raise into
`manifest.json`'s honest `status: "off"` - no second on/off mechanism.

**What this ticket actually builds**: the `CH-<hash>`/`MSG-<hash>` id
scheme and the `x-inference` extension shape, as real, pure, unit-tested
functions over synthetic `ChannelObservation`/`MessageObservation`
fixtures - ready for whenever a future detection pass can supply the real
thing. `build_asyncapi_document` is not wired to `generate()` at all
today; there is no store method to call it with.

**Distinct id family from `EP-<hash>`.** ADR-0013 defined `EP-<hash>` as
specifically `method + host + path_pattern` - a WebSocket channel has no
HTTP method to build that from, and reusing `EP-` here would quietly
widen what it means. `CH-<hash>`/`MSG-<hash>` are their own members of
the Short hash family (`CONTEXT.md`).

**SSE and long-polling ride the generic `http` binding** (point 4):
AsyncAPI's official bindings catalog has no first-class binding for
either (confirmed against the bindings repo), so both are `x-sse-stream`/
`x-long-polling` flags on `http` rather than being split into
`openapi.yaml` on the technicality that the handshake is a plain HTTP GET
- one traffic pattern, one document.

Details: docs/dev/generators/asyncapi.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.short_hash import short_hash

ASYNCAPI_VERSION = "3.0.0"

# Same "how many independent observations back this" scaling
# `generators/openapi.py::_confidence` uses (ADR-0004) - not HTTP-specific,
# reused rather than re-invented for message-shape confidence.
_CONFIDENCE_CEILING_OBSERVATIONS = 5


@dataclass(frozen=True)
class ChannelObservation:
    """What a future WS/SSE/long-polling detection pass would need to
    describe one channel - synthetic today; no real capture produces
    this yet.

    `protocol` is `"ws"` for a real WebSocket channel, `"http"` for an
    SSE stream or a long-polling endpoint (point 4) - `is_sse`/
    `is_long_polling` distinguish the two `"http"` cases from each other
    and from an ordinary request `openapi.yaml` already describes.
    Details: docs/dev/generators/asyncapi.md#channelobservation
    """

    protocol: str
    host: str
    address: str
    is_sse: bool = False
    is_long_polling: bool = False


@dataclass(frozen=True)
class MessageObservation:
    """One distinct message shape observed on a channel - synthetic
    today, the same "one bucket per distinct shape, observation_count
    tallies repeats" idea `InferredRequest` already applies to HTTP.
    Details: docs/dev/generators/asyncapi.md#messageobservation
    """

    channel_address: str
    name: str
    payload_shape: str
    observation_count: int = 1


def channel_id(channel: ChannelObservation) -> str:
    """`CH-<hash>` (ADR-0018 point 1) - a hash of protocol + host +
    channel address, the composite identity of one channel.
    Details: docs/dev/generators/asyncapi.md#channel_id
    """
    return f"CH-{short_hash(f'{channel.protocol}://{channel.host}{channel.address}')}"


def message_id(message: MessageObservation) -> str:
    """`MSG-<hash>` (ADR-0018 point 1) - a hash of channel address +
    message name, since the same message name can mean different things
    on two different channels.
    Details: docs/dev/generators/asyncapi.md#message_id
    """
    return f"MSG-{short_hash(f'{message.channel_address}|{message.name}')}"


def _channel_bindings(channel: ChannelObservation) -> Dict[str, Any]:
    """AsyncAPI's real `ws` binding for a genuine WebSocket channel;
    `http` plus a custom `x-sse-stream`/`x-long-polling` flag for the two
    traffic shapes the spec has no first-class binding for at all (point 4).
    Details: docs/dev/generators/asyncapi.md#_channel_bindings
    """
    if channel.protocol == "ws":
        return {"ws": {}}
    bindings: Dict[str, Any] = {"http": {}}
    if channel.is_sse:
        bindings["x-sse-stream"] = True
    if channel.is_long_polling:
        bindings["x-long-polling"] = True
    return bindings


def _message_confidence(message: MessageObservation) -> float:
    return round(min(1.0, message.observation_count / _CONFIDENCE_CEILING_OBSERVATIONS), 2)


def _message_inference(message: MessageObservation) -> Dict[str, Any]:
    """The `x-inference` extension (ADR-0018 point 2, reusing `openapi`'s
    exact pattern from ADR-0004 - AsyncAPI has no native metadata hook
    beyond `x-` vendor extensions either).
    Details: docs/dev/generators/asyncapi.md#_message_inference
    """
    return {
        "observation_count": message.observation_count,
        "confidence": {"payload_shape": _message_confidence(message)},
        # Reserved: the same interaction:<id>/har:<id> evidence-pointer
        # gap every other document in this map left reserved
        # (ADR-0017), never populated without a stable per-observation
        # id scheme to cite.
        "derived_from": [],
    }


def _message_entry(message: MessageObservation) -> Dict[str, Any]:
    return {
        "name": message.name,
        "payload": {"description": message.payload_shape} if message.payload_shape else {},
        "x-inference": _message_inference(message),
    }


def _channel_entry(channel: ChannelObservation, message_ids: List[str]) -> Dict[str, Any]:
    return {
        "address": channel.address,
        "bindings": _channel_bindings(channel),
        "messages": {msg_id: {"$ref": f"#/components/messages/{msg_id}"} for msg_id in message_ids},
    }


def build_asyncapi_document(
    channels: Sequence[ChannelObservation], messages: Sequence[MessageObservation], site: str
) -> Dict[str, Any]:
    """The full `asyncapi.json` payload - not wired to `generate()` today
    (see the module docstring), but real and callable for whenever it is.
    Details: docs/dev/generators/asyncapi.md#build_asyncapi_document
    """
    channel_ids = {channel.address: channel_id(channel) for channel in channels}
    messages_by_channel: Dict[str, List[MessageObservation]] = {}
    for message in messages:
        messages_by_channel.setdefault(message.channel_address, []).append(message)

    return {
        "asyncapi": ASYNCAPI_VERSION,
        "info": {"title": f"{site} async traffic", "version": "1.0.0"},
        "channels": {
            channel_ids[channel.address]: _channel_entry(
                channel, [message_id(message) for message in messages_by_channel.get(channel.address, [])]
            )
            for channel in channels
        },
        "components": {
            "messages": {message_id(message): _message_entry(message) for message in messages},
        },
    }


@DOCUMENT_REGISTRY.register("asyncapi")
class AsyncAPIDocument(DocumentGenerator):
    """Registered so `manifest.json` can enumerate it as `status: "off"`
    (ADR-0018 point 3) - not so it can actually run. `generate` always
    raises; there is no store method to call `build_asyncapi_document`
    with, since no capture instrumentation exists to have written one
    against.
    Details: docs/dev/generators/asyncapi.md#asyncapidocument
    """

    name = "asyncapi"
    title = "Async API"
    purpose = "WebSocket/SSE/long-polling message contract - absent until capture instrumentation for any of the three exists."

    def generate(self, request: DocumentRequest) -> str:
        raise NotImplementedError(
            "asyncapi.json has no capture instrumentation yet (docs/adr/0018 point 3) - "
            "WebSocket/SSE/long-polling detection is a future effort, out of this map's scope."
        )
