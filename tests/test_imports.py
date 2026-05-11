import importlib

def test_imports():
    importlib.import_module('src.interfaces')
    importlib.import_module('src.scrapers.playwright_scraper')
    importlib.import_module('src.agents.openai_agent')
    importlib.import_module('src.generators.prd_generator')
