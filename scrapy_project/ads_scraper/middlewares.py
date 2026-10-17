def _host(url):
    return url.split('/')[2] if '://' in url else ''


class ProxyMiddleware:
    """Route requests for PROXY_HOSTS through PROXY_URL (when it is set).

    Only reklama5: outside North Macedonia it redirects every URL to
    reklama5.com, a machine-translated English copy of the site, so runs on
    GitHub's (US) servers need a Macedonian IP. pazar3 works from anywhere
    and stays direct, so it doesn't use up the proxy's paid traffic, unless
    it blocks the runner (FALLBACK_HOSTS below).
    PROXY_URL may carry credentials (http://user:pass@host:port); Scrapy's
    HttpProxyMiddleware (order 750, after this one) turns them into the
    Proxy-Authorization header, which scrapy-impersonate also honours.
    """

    PROXY_HOSTS = ('reklama5.mk',)

    # pazar3 now and then answers a GitHub runner with 403 from the very
    # first page (the daily crawl got 0 ads on 2026-10-13, 14 and 15 while
    # other pazar3 crawls the same evenings went through). Then that request
    # is retried through the proxy, and so is every later pazar3 request of
    # the run, since the runner's IP stays the same. Only blocked runs use
    # the proxy's traffic, and only crawls that have PROXY_URL: the daily
    # one has it, the pazar3 backfills deliberately don't (one blocked
    # description backfill alone would be ~270 MB of the 10 GB/month plan).
    FALLBACK_HOSTS = ('pazar3.mk',)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get('PROXY_URL'))

    def __init__(self, proxy_url):
        self.proxy_url = proxy_url
        self.fallback = False

    def process_request(self, request, spider):
        host = _host(request.url)
        if self.proxy_url and (host.endswith(self.PROXY_HOSTS)
                               or (self.fallback and host.endswith(self.FALLBACK_HOSTS))):
            request.meta['proxy'] = self.proxy_url

    def process_response(self, request, response, spider):
        if (response.status == 403 and self.proxy_url and not request.meta.get('proxy')
                and _host(request.url).endswith(self.FALLBACK_HOSTS)):
            if not self.fallback:
                spider.logger.warning('pazar3 answered 403 at %s: going through the proxy for the rest of this run',
                                      request.url)
                self.fallback = True
            # the workflow's crawl health check subtracts these from the 403 count
            spider.crawler.stats.inc_value('proxy_fallback/403')
            return request.replace(dont_filter=True)
        return response


class ImpersonateMiddleware:
    """Send requests to sites that fingerprint TLS through a real-browser TLS
    stack (curl_cffi via scrapy-impersonate) instead of Twisted's.

    reklama5 answers Scrapy's own TLS handshake with 403 regardless of
    headers — the same request with identical headers, from the same IP,
    succeeds from python-requests and from curl_cffi impersonating Chrome.
    Other sites keep the default downloader (the handler only switches on
    this meta key).
    """

    IMPERSONATE_HOSTS = ('reklama5.mk',)

    def process_request(self, request, spider):
        if _host(request.url).endswith(self.IMPERSONATE_HOSTS):
            request.meta.setdefault('impersonate', 'chrome')
