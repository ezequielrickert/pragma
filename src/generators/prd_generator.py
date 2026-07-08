"""
PRD Generator implementation using a planned, multi-skill autonomous loop.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional

from ..core.interfaces import Agent, PageState, PRDGenerator, Scraper, parse_action
from ..core.registry import GENERATOR_REGISTRY
from ..utils.io import write_output


@GENERATOR_REGISTRY.register("simple")
class SimplePRDGenerator(PRDGenerator):
    """Orchestrates an agent through discovery and structural synthesis."""

    def __init__(
        self,
        agent: Agent,
        scraper: Scraper,
        progress_file: str = "PROGRESS.md",
        max_iterations: int = 12,
    ) -> None:
        """Initialize with brain (agent), hands (scraper), and progress tracker."""
        self.agent = agent
        self.scraper = scraper
        self.progress_file = progress_file
        self.max_iterations = max_iterations
        # Load specialized skills
        self.archeologist_skill = self._load_skill("archeologist-skill")
        self.dom_mapper_skill = self._load_skill("dom-mapper-skill")
        self.progress_skill = self._load_skill("archaeology-progress-tracker")
        
        # Track discovery state
        self.routes: Dict[str, Dict[str, Any]] = {}
        self.base_domain: Optional[str] = None

    def _load_skill(self, skill_name: str) -> Optional[str]:
        """Load a specific skill from the .gemini/skills directory."""
        root = pathlib.Path(__file__).resolve().parents[2]
        skill_path = root / ".gemini" / "skills" / skill_name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")
        return None

    def generate_prd(self, url: str) -> str:
        """Execute a deep research loop and synthesize the final tree map."""
        print(f"Phase 1/4: Deep Discovery on {url}")
        state = self.scraper.navigate(url)

        # Initialize discovery tracking
        self.base_domain = self._get_domain(url)
        self._add_route(url, status="Finished", components=len(state.components), context="Root")
        self._update_discovered_routes(state.links, source=url)

        print("Phase 2/4: Planning Exhaustive Research Strategy")
        plan = self._create_plan(state)
        self._update_progress("PLAN CREATED", plan)

        print("Phase 3/4: Executing High-Fidelity Interaction Loop")
        self._execute_loop(state)

        print("Phase 4/4: Synthesizing Hierarchical System Mind-Map")
        return self._synthesize_tree_report()

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for filtering."""
        from urllib.parse import urlparse
        return urlparse(url).netloc

    def _add_route(self, url: str, status: str = "Pending", components: int = 0, context: str = "", label: str = "") -> None:
        """Add or update a route in the tracking map."""
        clean_url = url.split("#")[0].rstrip("/")
        if clean_url not in self.routes or status != "Pending":
            self.routes[clean_url] = {
                "status": status,
                "components": components,
                "visited": "2026-05-17" if status == "Finished" else "-",
                "context": context or self.routes.get(clean_url, {}).get("context", "-"),
                "label": label or self.routes.get(clean_url, {}).get("label", "-")
            }

    def _update_discovered_routes(self, links: list[Dict[str, str]], source: str) -> None:
        """Add new same-domain links to discovery list."""
        for link in links:
            href = link.get("href", "")
            if href and self._get_domain(href) == self.base_domain:
                self._add_route(href, context=source, label=link.get("text", ""))

    def _create_plan(self, state: PageState) -> str:
        """Create a step-by-step research plan for deep excavation."""
        pending = [u for u, d in self.routes.items() if d["status"] == "Pending"]
        prompt = (
            f"High-Fidelity Observation of {state.url}\n"
            f"Title: {state.title}\n"
            f"Detected Components: {len(state.components)}\n"
            f"Initial Discovered Routes: {json.dumps(pending)}\n"
            "Create a plan to exhaustively map this system's tree structure. "
            "You MUST explore all discovered routes to complete the map."
        )
        return self.agent.generate(prompt, system_instruction=self.archeologist_skill)

    def _update_progress(self, stage: str, details: str) -> None:
        """Maintain a persistent progress file with compact metrics."""
        visited = [u for u, d in self.routes.items() if d["status"] == "Finished"]
        
        total = len(self.routes)
        perc = (len(visited) / total * 100) if total > 0 else 0
        
        header = (
            f"# Archaeology Progress: {self.base_domain}\n\n"
            f"## Status: {len(visited)}/{total} ({perc:.1f}%)\n\n"
        )
        
        table = self._build_progress_table()
        content = f"{header}{table}\n\n## Log: {stage}\n\n{details}\n\n---\n"
        write_output(self.progress_file, content)

    def _build_progress_table(self) -> str:
        """Build a compact markdown table for route discovery progress."""
        table = "## Route Map\n\n| Route | Status | Label |\n|-------|--------|-------|\n"
        
        # List all routes to ensure the audit trail is complete
        rows = sorted(self.routes.items(), key=lambda x: (x[1]["status"] != "Finished", x[0]))
        for url, data in rows:
            table += f"| {url} | {data['status']} | {data['label']} |\n"
        return table

    def _execute_loop(self, state: PageState) -> None:
        """The core iteration loop for deep component discovery."""
        current_state = state
        for i in range(self.max_iterations):
            print(f"Research Iteration {i+1}...")

            prompt = self._build_iteration_prompt(current_state)
            system_instruction = f"{self.archeologist_skill}\n\n{self.progress_skill}"
            decision = self.agent.generate(prompt, system_instruction=system_instruction).strip()
            print(f"Action: {decision}")

            if parse_action(decision).kind == "finish":
                self._update_progress(f"ITERATION {i+1}", "Agent concluded research.")
                break

            next_state = self._execute_action(decision)
            if not next_state:
                break
                
            current_state = next_state
            self._handle_iteration_result(i + 1, decision, current_state)

    def _build_iteration_prompt(self, state: PageState) -> str:
        """Build a comprehensive prompt for a single discovery iteration."""
        pending = sorted([u for u, d in self.routes.items() if d["status"] == "Pending"])

        # Send ALL component data and ALL pending routes for maximum discovery quality
        return (
            f"URL: {state.url}\n"
            f"Pending: {json.dumps(pending)}\n"
            f"DNA: {json.dumps(state.components)}\n\n"
            "Action: GOTO <url>, CLICK <path>, or FINISH."
        )

    def _handle_iteration_result(self, iter_num: int, action: str, state: PageState) -> None:
        """Update state and progress after an iteration."""
        url = state.url.split("#")[0].rstrip("/")
        self._add_route(url, status="Finished", components=len(state.components))
        self._update_discovered_routes(state.links, source=url)

        self._update_progress(
            f"ITERATION {iter_num}",
            f"Action: {action}\nNow at: {state.url}\n"
            f"Components found: {len(state.components)}",
        )

    def _execute_action(self, decision: str) -> Optional[PageState]:
        """Execute the agent's chosen action."""
        action = parse_action(decision)
        try:
            if action.kind == "goto":
                return self.scraper.navigate(action.target)
            if action.kind == "click":
                selector = action.target
                if any(c in selector for c in (">", "#", ".")):
                    return self.scraper.click(selector)
                return self.scraper.click(f"text='{selector}'")
        except Exception as exc:
            print(f"Action failed: {exc}")
        return None

    def _synthesize_tree_report(self) -> str:
        """Synthesize final report using the DOM-Mapper skill."""
        try:
            path = pathlib.Path(self.progress_file)
            progress = path.read_text(encoding="utf-8")
            # Aggressive truncation for context window safety (8k chars ~ 2k tokens)
            if len(progress) > 8000:
                progress = "...(truncated)...\n" + progress[-8000:]

            prompt = (
                f"Full Research Log:\n{progress}\n\n"
                "Generate a Hierarchical System Mind-Map from this data."
            )
            return self.agent.generate(prompt, system_instruction=self.dom_mapper_skill)
        finally:
            self.scraper.close()
