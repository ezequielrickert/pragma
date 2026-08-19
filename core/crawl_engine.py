"""The `pragma crawl` entry point: a thin orchestrator chaining
`static → cluster → dynamic` against one URL.

Deliberately thin: no new crawling/analysis logic of its own, just the
three existing engines (`StaticEngine`, `ClusterEngine`, `DynamicEngine`)
called in sequence, each exactly as its own CLI command would run it.
Never runs `pragma docs` - docs stays a fully separate, explicit
invocation (the map's own Destination is explicit about this: `pragma
crawl` never auto-chains it).

Each phase writes straight to the persistent graph store as it runs, so
"preserve partial results on failure" needs no rollback machinery here -
a phase's writes are already committed to disk by the time it returns.
This orchestrator's whole job is to stop the chain at the first failure
and say clearly which phase it was, rather than to protect data that was
never at risk.
Details: docs/dev/core/crawl_engine.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from .cluster_engine import ClusterEngine, ClusterRunResult
from .config import PragmaConfig
from .dynamic_engine import DynamicEngine, DynamicRunResult
from .static_engine import StaticEngine, StaticRunResult


@dataclass
class CrawlRunResult:
    """`CrawlEngine.run()`'s return value - one result per phase that got
    to run, plus which phase (if any) stopped the chain early.
    `static`/`cluster`/`dynamic` are `None` exactly for the phases that
    never ran, so a caller can tell "ran and produced this" from "never
    got here" without a separate flag per phase.
    Details: docs/dev/core/crawl_engine.md#crawlrunresult
    """

    site: str
    static: Optional[StaticRunResult] = None
    cluster: Optional[ClusterRunResult] = None
    dynamic: Optional[DynamicRunResult] = None
    failed_phase: Optional[str] = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        """Details: docs/dev/core/crawl_engine.md#succeeded"""
        return self.failed_phase is None


class CrawlEngine:
    """Chains `pragma static` -> `pragma cluster` -> `pragma dynamic`
    against one URL, stopping at whichever phase fails first.
    Details: docs/dev/core/crawl_engine.md#crawlengine
    """

    def __init__(self, config: PragmaConfig) -> None:
        self.config = config
        self.site = urlparse(config.url).netloc if config.url else ""

    @classmethod
    def from_config(cls, config: PragmaConfig) -> "CrawlEngine":
        """Unlike every other engine's `from_config`, resolves nothing
        eagerly - no agent, no graph store. Each phase resolves its own
        via its own `from_config`, exactly as it would standalone; there
        is nothing shared to wire up front.
        Details: docs/dev/core/crawl_engine.md#from_config
        """
        return cls(config)

    async def run(self, url: str) -> CrawlRunResult:
        """Runs `static`, then `cluster`, then `dynamic`, in that order,
        against `url`. Stops and returns as soon as one phase raises -
        the phases that already ran keep whatever they wrote; nothing
        after the failure ever starts.
        Details: docs/dev/core/crawl_engine.md#run
        """
        site = self.site or urlparse(url).netloc
        result = CrawlRunResult(site=site)

        print(f"\n== pragma crawl: static ({site}) ==")
        try:
            result.static = await StaticEngine.from_config(self.config).run(url)
        except Exception as exc:
            return self._stop(result, "static", exc, f"pragma static {url}")

        print(f"\n== pragma crawl: cluster ({site}) ==")
        try:
            result.cluster = ClusterEngine.from_config(self.config, site).run()
        except Exception as exc:
            return self._stop(result, "cluster", exc, f"pragma cluster {site}")

        print(f"\n== pragma crawl: dynamic ({site}) ==")
        try:
            result.dynamic = await DynamicEngine.from_config(self.config).run(url)
        except Exception as exc:
            return self._stop(result, "dynamic", exc, f"pragma dynamic {url}")

        return result

    def _stop(
        self, result: CrawlRunResult, phase: str, exc: Exception, resume_command: str
    ) -> CrawlRunResult:
        """Records which phase failed and why, and names the standalone
        command that would resume from exactly what the earlier phases
        already wrote - the practical version of "preserves partial
        results on failure": nothing is lost, and the next step to take
        is spelled out rather than left for the caller to work out.
        Details: docs/dev/core/crawl_engine.md#_stop
        """
        result.failed_phase = phase
        result.error = str(exc)
        print(f"pragma crawl stopped at the {phase!r} phase: {exc}")
        print(f"Earlier phases' data is intact - resume with: {resume_command}")
        return result
