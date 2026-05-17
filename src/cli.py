"""
Command-line interface for Pragma.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import datetime

from dotenv import load_dotenv

# Path setup to allow running from project root
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(override=True)

from src.agents.factory import AgentFactory
from src.generators.prd_generator import SimplePRDGenerator
from src.scrapers.playwright_scraper import PlaywrightScraper
from src.utils.io import write_output


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Pragma: Autonomous Web-App Archaeology")
    parser.add_argument("--url", "-u", help="URL to explore", default=os.getenv("URL"))
    parser.add_argument("--out", "-o", help="Output folder for PRDs", default="docs")
    parser.add_argument("--logs", "-l", help="Folder for research logs", default="research_logs")
    parser.add_argument("--provider", "-p", help="Agent provider (gemini/openai/mock)")
    args = parser.parse_args()

    if not args.url:
        parser.error("URL must be provided via --url or URL env var")
    return args


def generate_timestamp() -> str:
    """Generate a standard timestamp string."""
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def slugify(url: str) -> str:
    """Turn URL into a filesystem-safe slug."""
    return url.replace("https://", "").replace("http://", "").replace("/", "_")


def main() -> None:
    """Main execution entry point."""
    args = parse_args()
    timestamp = generate_timestamp()
    slug = slugify(args.url)

    # Prepare paths
    prd_path = f"{args.out}/{slug}_prd_{timestamp}.md"
    log_path = f"{args.logs}/{slug}_research_{timestamp}.md"

    scraper = PlaywrightScraper(headless=True)
    agent = AgentFactory.create_agent(args.provider)
    prd_gen = SimplePRDGenerator(agent, scraper, progress_file=log_path)

    try:
        print(f"Starting autonomous archaeology for: {args.url}")
        prd = prd_gen.generate_prd(args.url)

        write_output(prd_path, prd)
        print(f"Successfully generated PRD: {prd_path}")
        print(f"Detailed research log saved to: {log_path}")

    except Exception as exc:
        print(f"Critical error during exploration: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
