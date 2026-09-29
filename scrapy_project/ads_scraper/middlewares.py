def _host(url):
    return url.split('/')[2] if '://' in url else ''


class ProxyMiddleware:
    """Route requests for PROXY_HOSTS through PROXY_URL (when it is set).

    Only reklama5: outside North Macedonia it redirects every URL to
    reklama5.com, a machine-translated English copy of the site, so runs on
    GitHub's (US) servers need a Macedonian IP. pazar3 works from anywhere
    and stays direct, so it doesn't use up the proxy's paid traffic.
    PROXY_URL may carry credentials (http://user:pass@host:port); Scrapy's
    HttpProxyMiddleware (order 750, after this one) turns them into the
    Proxy-Authorization header, which scrapy-impersonate also honours.
    """

    PROXY_HOSTS = ('reklama5.mk',)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get('PROXY_URL'))

    def __init__(self, proxy_url):
        self.proxy_url = proxy_url

    def process_request(self, request, spider):
        if self.proxy_url and _host(request.url).endswith(self.PROXY_HOSTS):
            request.meta['proxy'] = self.proxy_url


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
