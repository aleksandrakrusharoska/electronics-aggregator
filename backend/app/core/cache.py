"""Caching for read-heavy, rarely-changing endpoints.

The analytics endpoints in app/api/ads.py each page through the entire ads
view and recompute statistics, even though the underlying data only changes
once a day (the scheduled scraping/agent pipeline).

- cached(ttl): an in-process TTL cache — avoids repeating the scan on every
  page load, but is empty again after every restart, and Render puts the
  service to sleep after 15 idle minutes.
- snapshot(name): reads the result the daily workflow precomputed into the
  analytics_snapshots table (backend/precompute_analytics.py), so even the
  first request after a wake-up is a single small read. Falls back to
  computing it (and caching that in memory) if there is no snapshot yet.
"""
import functools
import logging
import time

log = logging.getLogger(__name__)

_cache: dict[tuple, tuple[float, object]] = {}
SNAPSHOT_TTL = 3600   # re-read the snapshot table at most hourly per process


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


def snapshot_key(name: str, kwargs: dict) -> str:
    """'brands' + {'source': 'pazar3'} -> 'brands:source=pazar3' (None args left out)."""
    params = '&'.join(f'{k}={v}' for k, v in sorted(kwargs.items()) if v is not None)
    return f'{name}:{params}' if params else name


def snapshot(name: str):
    """Serve the precomputed result for this endpoint (and its arguments) from
    analytics_snapshots; compute it directly only when there is none. The
    undecorated function stays reachable as `fn.compute` for the precompute
    job."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(**kwargs):
            key = snapshot_key(name, kwargs)
            now = time.monotonic()
            entry = _cache.get(('snapshot', key))
            if entry is not None and now - entry[0] < SNAPSHOT_TTL:
                return entry[1]
            result = None
            try:
                from app.core.supabase import get_supabase
                rows = (get_supabase().table('analytics_snapshots').select('data')
                        .eq('name', key).limit(1).execute().data)
                if rows:
                    result = rows[0]['data']
            except Exception as exc:   # table missing / DB hiccup: compute instead
                log.warning('Analytics snapshot %s unavailable: %s', key, exc)
            if result is None:
                result = fn(**kwargs)
            _cache[('snapshot', key)] = (now, result)
            return result
        wrapper.compute = fn
        wrapper.snapshot_name = name
        return wrapper
    return decorator
