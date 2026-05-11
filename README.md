POC: Modular Scraper + Agent PRD Generator (Python)

Usage:
- Copy .env.example to .env and set URL and GEMINI_API_KEY (or OPENAI_API_KEY for OpenAI)
- To use Gemini: set AGENT_PROVIDER=gemini and optionally GEMINI_MODEL in .env
- pip install -r requirements.txt
- python -m playwright install
- python src/cli.py --url https://example.com

Design: modular interfaces for Scraper, Agent, PRDGenerator. Swap implementations by changing imports or wiring in CLI.
