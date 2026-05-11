import sys
import os
import argparse
import pathlib
from datetime import datetime
# Ensure project root on sys.path so script can be run directly
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Load .env if present
from dotenv import load_dotenv
load_dotenv(override=True)

from src.scrapers.playwright_scraper import PlaywrightScraper
from src.agents.openai_agent import OpenAIAgent
from src.generators.prd_generator import SimplePRDGenerator
from src.utils.io import write_output

def main():
    parser = argparse.ArgumentParser(description='POC: scrape URL and generate PRD')
    parser.add_argument('--url', '-u', help='URL to scrape', default=os.getenv('URL'))
    parser.add_argument('--out', '-o', help='Output folder', default='docs')
    args = parser.parse_args()
    if not args.url:
        parser.error('URL must be provided via --url or URL env var')

    scraper = PlaywrightScraper(headless=True)
    scraped = scraper.scrape(args.url)

    # Choose agent provider: 'openai' (default) or 'gemini'.
    provider = os.getenv('AGENT_PROVIDER', 'openai').lower()
    from src.run_sample import MockAgent

    if provider == 'gemini':
        try:
            # Prefer OAuth service-account flow if credentials file is present
            if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
                from src.agents.gemini_oauth_agent import GeminiOAuthAgent
                agent = GeminiOAuthAgent(creds_file=os.getenv('GOOGLE_APPLICATION_CREDENTIALS'), model=os.getenv('GEMINI_MODEL'))
            else:
                from src.agents.gemini_agent import GeminiAgent
                gemini_key = os.getenv('GEMINI_API_KEY') or os.getenv('OPENAI_API_KEY')
                agent = GeminiAgent(api_key=gemini_key, model=os.getenv('GEMINI_MODEL'))
        except Exception as e:
            print('Failed to initialize Gemini agent:', e)
            agent = MockAgent()
    elif provider == 'openai':
        if os.getenv('OPENAI_API_KEY'):
            try:
                agent = OpenAIAgent()
            except Exception as e:
                print('Failed to initialize OpenAIAgent:', e)
                agent = MockAgent()
        else:
            agent = MockAgent()
    else:
        print(f'Unknown AGENT_PROVIDER "{provider}", falling back to MockAgent')
        agent = MockAgent()

    prd_gen = SimplePRDGenerator(agent)
    try:
        prd = prd_gen.generate_prd(scraped)
    except Exception as e:
        print('Agent generation failed:', e)
        # Provide actionable guidance for common Gemini errors
        err_text = str(e).lower()
        if '404' in err_text or 'not found' in err_text:
            print('\nGemini API returned 404. This usually means the API key is not linked to a Google Cloud project with the Generative Language API enabled, or the chosen model is not available to the key.')
            print("Recommendations:\n - Ensure the Generative Language API is enabled in the GCP project that owns the API key.\n - Use a model available to your key (e.g., models/gemini-flash-latest) or use OAuth (service account).\n - To use OAuth, set the GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service account JSON and retry.")
        elif '403' in err_text or 'permission' in err_text or 'forbidden' in err_text:
            print('\nGemini API returned a permission error. Ensure the API key has access and is not IP- or ref-restricted, or use a service account with proper roles.')
        from src.run_sample import MockAgent
        prd = SimplePRDGenerator(MockAgent()).generate_prd(scraped)

    slug = args.url.replace('https://','').replace('http://','').replace('/','_')
    filename = f"{args.out}/{slug}_prd_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.md"
    write_output(filename, prd)
    print('PRD written to', filename)

if __name__ == '__main__':
    main()
