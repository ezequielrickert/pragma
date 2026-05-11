from typing import Dict
from ..interfaces import PRDGenerator

class SimplePRDGenerator(PRDGenerator):
    def __init__(self, agent):
        self.agent = agent

    def generate_prd(self, scraped: Dict) -> str:
        prompt = (
            "You are a product writer. Create a concise Product Requirements Document (PRD) in markdown.\n"
            "Input HTML:\n" + (scraped.get('html')[:2000] if scraped.get('html') else '') + "\n\n"
            "Important links:\n" + '\n'.join(scraped.get('links', [])[:20]) + "\n\n"
            "Produce sections: Summary, Goals, Users, Key Features, Page Breakdown (list key areas), Acceptance Criteria, Notes."
        )
        return self.agent.generate(prompt)
