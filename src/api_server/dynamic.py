"""`/dynamic/*` - browser actions, wrapping `PlaywrightScraper`'s methods 1:1.

Model-facing action names (`navigate`/`click`/`fill`/`submit`) map directly to these routes;
`get_state` is a read-only addition useful for manual debugging (see ARCHITECTURE.md). `finish`
has no route here - it's pure control flow in `SimplePRDGenerator`'s loop with no Playwright
counterpart, same as before.

`ref -> selector` resolution never happens here - `SimplePRDGenerator` resolves that itself
(`_dna_index_map`) before calling any of these routes with an already-resolved CSS selector.
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import playwright_runtime

router = APIRouter(prefix="/dynamic", tags=["dynamic"])


class NavigateRequest(BaseModel):
    url: str


class ClickRequest(BaseModel):
    selector: str


class FillRequest(BaseModel):
    selector: str
    value: str


class SubmitRequest(BaseModel):
    selector: str


async def _call(func) -> dict:
    """Run a scraper call and convert its PageState result, or raise a 502 with the real error.

    A Playwright failure (bad/ambiguous selector, timeout, etc.) is a real, meaningful signal to
    the caller - not swallowed here, mirroring PlaywrightScraper's own raise-on-real-failure
    contract (see its click()/fill() docstrings).
    """
    try:
        state = await playwright_runtime.run(func)
    except Exception as exc:  # noqa: BLE001 - deliberately surfaced to the client, not logged-and-swallowed
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return dataclasses.asdict(state)


@router.post("/navigate")
async def navigate(body: NavigateRequest) -> dict:
    return await _call(lambda scraper: scraper.navigate(body.url))


@router.post("/click")
async def click(body: ClickRequest) -> dict:
    return await _call(lambda scraper: scraper.click(body.selector))


@router.post("/fill")
async def fill(body: FillRequest) -> dict:
    return await _call(lambda scraper: scraper.fill(body.selector, body.value))


@router.post("/submit")
async def submit(body: SubmitRequest) -> dict:
    return await _call(lambda scraper: scraper.submit(body.selector))


@router.get("/state")
async def get_state() -> dict:
    return await _call(lambda scraper: scraper.get_state())
