class ProxyMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get('PROXY_URL'))

    def __init__(self, proxy_url):
        self.proxy_url = proxy_url

    def process_request(self, request, spider):
        if self.proxy_url:
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
        host = request.url.split('/')[2] if '://' in request.url else ''
        if host.endswith(self.IMPERSONATE_HOSTS):
            request.meta.setdefault('impersonate', 'chrome')
