"""
Simple sample script to run Pragma exploration.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Path setup
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(override=True)

from src.agents.factory import AgentFactory
from src.generators.prd_generator import SimplePRDGenerator
from src.scrapers.playwright_scraper import PlaywrightScraper


def slugify(url: str) -> str:
    """Turn URL into a filesystem-safe slug."""
    return url.replace("https://", "").replace("http://", "").replace("/", "_")


def main() -> None:
    """Sample execution loop."""
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    args = parser.parse_args()

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    slug = slugify(args.url)
    
    log_path = f"research_logs/{slug}_research_{timestamp}.md"
    prd_path = f"docs/{slug}_prd_{timestamp}.md"

    scraper = PlaywrightScraper(headless=True)
    agent = AgentFactory.create_agent()

    prd_gen = SimplePRDGenerator(agent, scraper, progress_file=log_path)
    prd = prd_gen.generate_prd(args.url)

    # Final PRD save
    Path(prd_path).parent.mkdir(parents=True, exist_ok=True)
    Path(prd_path).write_text(prd, encoding="utf-8")
    
    print(f"Wrote PRD to {prd_path}")
    print(f"Wrote Research Log to {log_path}")


if __name__ == "__main__":
    main()
