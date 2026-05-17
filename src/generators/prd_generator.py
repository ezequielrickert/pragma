"""
PRD Generator implementation using a planned, multi-skill autonomous loop.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional

from ..interfaces import Agent, PRDGenerator, Scraper
from ..utils.io import write_output


class SimplePRDGenerator(PRDGenerator):
    """Orchestrates an agent through discovery and structural synthesis."""

    def __init__(
        self, agent: Agent, scraper: Scraper, progress_file: str = "PROGRESS.md"
    ) -> None:
        """Initialize with brain (agent), hands (scraper), and progress tracker."""
        self.agent = agent
        self.scraper = scraper
        self.progress_file = progress_file
        # Load specialized skills
        self.archeologist_skill = self._load_skill("archeologist-skill")
        self.dom_mapper_skill = self._load_skill("dom-mapper-skill")

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

        print("Phase 2/4: Planning Exhaustive Research Strategy")
        plan = self._create_plan(state)
        self._update_progress("PLAN CREATED", plan)

        print("Phase 3/4: Executing High-Fidelity Interaction Loop")
        self._execute_loop(state)

        print("Phase 4/4: Synthesizing Hierarchical System Mind-Map")
        return self._synthesize_tree_report()

    def _create_plan(self, state: Dict[str, Any]) -> str:
        """Create a step-by-step research plan for deep excavation."""
        prompt = (
            f"High-Fidelity Observation of {state['url']}\n"
            f"Title: {state['title']}\n"
            f"Detected Components: {len(state['components'])}\n"
            "Create a plan to exhaustively map this system's tree structure."
        )
        # Use Archeologist skill for planning
        return self.agent.generate(prompt, system_instruction=self.archeologist_skill)

    def _update_progress(self, stage: str, details: str) -> None:
        """Maintain a persistent progress file tracking the agent's work."""
        content = f"# Research Progress: {stage}\n\n{details}\n\n---\n"
        current = ""
        path = pathlib.Path(self.progress_file)
        if path.exists():
            current = path.read_text(encoding="utf-8")
        write_output(self.progress_file, current + content)

    def _execute_loop(self, state: Dict[str, Any]) -> None:
        """The core iteration loop for deep component discovery."""
        current_state = state
        for i in range(8):
            print(f"Research Iteration {i+1}...")

            path = pathlib.Path(self.progress_file)
            progress_context = path.read_text(encoding="utf-8")[-3000:] if path.exists() else ""

            prompt = (
                f"Current Progress: {progress_context}\n\n"
                f"Current Page: {current_state['url']}\n"
                f"Page Components (DNA): {json.dumps(current_state['components'][:30])}\n"
                "Decide your next action. Commands: GOTO <url>, CLICK <text/path>, or FINISH."
            )

            # Use Archeologist skill for interaction
            decision = self.agent.generate(prompt, system_instruction=self.archeologist_skill).strip()
            print(f"Action: {decision}")

            if decision.startswith("FINISH"):
                self._update_progress(f"ITERATION {i+1}", "Agent concluded research.")
                break

            next_state = self._execute_action(decision)
            if next_state:
                current_state = next_state
                self._update_progress(
                    f"ITERATION {i+1}",
                    f"Action: {decision}\nNow at: {current_state['url']}\n"
                    f"Components found: {len(current_state['components'])}",
                )
            else:
                break

    def _execute_action(self, decision: str) -> Optional[Dict[str, Any]]:
        """Execute the agent's chosen action."""
        try:
            if decision.startswith("GOTO"):
                url = decision.replace("GOTO", "").strip()
                return self.scraper.navigate(url)
            if decision.startswith("CLICK"):
                selector = decision.replace("CLICK", "").strip()
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
            
            # Truncate to last 15,000 characters to stay within safety limits for large explorations
            if len(progress) > 15000:
                progress = "...(truncated)...\n" + progress[-15000:]

            prompt = (
                f"Full Research Log:\n{progress}\n\n"
                "Based on the discovery data, generate a final Hierarchical System Mind-Map. "
                "Show all branches from the root page down to the leaf components and routes."
            )
            report = self.agent.generate(prompt, system_instruction=self.dom_mapper_skill)
            return report
        finally:
            self.scraper.close()
