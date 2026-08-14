# `core/bootstrap.py`

## module

Import this module once (from the CLI or tests) before using the
registries. Optional-dependency plugins are guarded so a missing package
never breaks startup.

Post-crawl4ai-migration: `spiders/` (`Crawl4AICrawler`,
`MechanicalCrawler`, `GraphStoreSink`) is wired directly by `Engine`, not
through a registry - there's exactly one crawling implementation now,
unlike agents/graph stores which genuinely have multiple.
