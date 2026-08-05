"""
Run the LangChain orchestrator agent.

The orchestrator checks the current pipeline state and automatically runs
whichever agents are needed, in the correct order.

Usage:
    python run_orchestrator.py                  # full pipeline, parse up to 200 ads
    python run_orchestrator.py --limit 500      # parse up to 500 ads
    python run_orchestrator.py --skip-parser    # skip LLM parsing (faster)

Individual agents can still be run manually at any time:
    python run_classification_agent.py
    python run_parser_agent.py --limit 500
    python run_dedup_agent.py
    python run_clustering_agent.py
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Run the orchestrator agent')
    parser.add_argument('--limit', type=int, default=200,
                        help='Max ads to parse per run (default: 200)')
    parser.add_argument('--skip-parser', action='store_true',
                        help='Skip the LLM parsing step')
    args = parser.parse_args()

    for var in ('SUPABASE_URL', 'SUPABASE_KEY', 'GROQ_API_KEY'):
        if not os.getenv(var):
            sys.exit(f'Missing {var} in .env')

    from agents.orchestrator_agent import run_orchestrator

    log.info('Starting orchestrator (parser_limit=%d, skip_parser=%s)',
             args.limit, args.skip_parser)

    summary = run_orchestrator(
        parser_limit=args.limit,
        skip_parser=args.skip_parser,
    )

    print('\n' + '─' * 60)
    print(summary)
    print('─' * 60)


if __name__ == '__main__':
    main()
