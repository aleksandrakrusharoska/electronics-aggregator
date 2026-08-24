class ProxyMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get('PROXY_URL'))

    def __init__(self, proxy_url):
        self.proxy_url = proxy_url

    def process_request(self, request, spider):
        if self.proxy_url:
            request.meta['proxy'] = self.proxy_url
