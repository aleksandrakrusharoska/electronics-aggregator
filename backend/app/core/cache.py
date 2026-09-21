"""In-process TTL cache for read-heavy, rarely-changing endpoints.

The analytics endpoints in app/api/ads.py each page through the entire
`ads` table and recompute statistics on every request, even though the
underlying data only changes once a day (the scheduled scraping/agent
pipeline). Caching the result for a while avoids repeating that full
table scan on every page load without needing Redis for a single-process
deployment.
"""
import functools
import time

_cache: dict[tuple, tuple[float, object]] = {}


def cached(ttl_seconds: int):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (fn.__qualname__, args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            entry = _cache.get(key)
            if entry is not None and now - entry[0] < ttl_seconds:
                return entry[1]
            result = fn(*args, **kwargs)
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator
