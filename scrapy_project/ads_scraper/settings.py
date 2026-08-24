import os
from dotenv import load_dotenv
load_dotenv()

BOT_NAME = 'ads_scraper'

SPIDER_MODULES = ['ads_scraper.spiders']
NEWSPIDER_MODULE = 'ads_scraper.spiders'

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/125.0.0.0 Safari/537.36'
)

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 4
DOWNLOAD_DELAY = 1.5

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.5
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 429]

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

PROXY_URL = os.getenv('PROXY_URL')

DOWNLOADER_MIDDLEWARES = {
    'ads_scraper.middlewares.ProxyMiddleware': 350,
}

ITEM_PIPELINES = {
    'ads_scraper.pipelines.NormalizePipeline': 200,
    'ads_scraper.pipelines.IncrementalCheckPipeline': 250,
    'ads_scraper.pipelines.JsonWriterPipeline': 300,
    'ads_scraper.pipelines.SupabasePipeline': 400,
}

INCREMENTAL = False  # set to True via -s INCREMENTAL=1 for daily runs
