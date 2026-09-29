"""
Resolve names to lookup-table IDs (sources, categories, locations, brands,
models, clusters) for writes into the normalized schema.

Spiders and agents still work with plain names ("pazar3", "Samsung",
"Galaxy S21"); this module turns them into the foreign keys that `ads`
now stores, creating a lookup row the first time a name is seen. Each
table is loaded once per process and cached, so resolving a name is a dict
lookup, not a query.

Brands and models are matched case-insensitively ("HP" == "Hp"), the same
way the migration merged the existing spellings.
"""
import logging

logger = logging.getLogger(__name__)

PAGE = 1000


def _clean(name) -> str | None:
    if name is None:
        return None
    name = str(name).strip()
    return name or None


def _fetch_all(client, table: str, columns: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        batch = client.table(table).select(columns).range(offset, offset + PAGE - 1).execute().data
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


class Lookups:
    def __init__(self, client):
        self._client = client
        self._sources: dict[str, int] | None = None
        self._categories: dict[tuple[int, str], int] | None = None
        self._locations: dict[str, int] | None = None
        self._brands: dict[str, int] | None = None
        self._models: dict[tuple[int, str], int] | None = None

    # -- loading (lazy, so a spider that never writes a brand never loads brands)

    def _load_sources(self):
        if self._sources is None:
            self._sources = {r['name']: r['source_id'] for r in _fetch_all(self._client, 'sources', 'source_id, name')}

    def _load_categories(self):
        if self._categories is None:
            rows = _fetch_all(self._client, 'categories', 'category_id, source_id, name')
            self._categories = {(r['source_id'], r['name']): r['category_id'] for r in rows}

    def _load_locations(self):
        if self._locations is None:
            self._locations = {r['name']: r['location_id'] for r in _fetch_all(self._client, 'locations', 'location_id, name')}

    def _load_brands(self):
        if self._brands is None:
            self._brands = {r['name'].lower(): r['brand_id'] for r in _fetch_all(self._client, 'brands', 'brand_id, name')}

    def _load_models(self):
        if self._models is None:
            rows = _fetch_all(self._client, 'models', 'model_id, brand_id, name')
            self._models = {(r['brand_id'], r['name'].lower()): r['model_id'] for r in rows}

    def _insert(self, table: str, row: dict, id_column: str, refetch) -> int:
        """Insert a new lookup row; if another process inserted the same name
        in the meantime (unique violation), read back its ID instead."""
        try:
            return self._client.table(table).insert(row).execute().data[0][id_column]
        except Exception as exc:
            existing = refetch()
            if existing:
                return existing[0][id_column]
            raise exc

    # -- public API: name -> ID (None stays None)

    def source_id(self, name, create: bool = True) -> int | None:
        name = _clean(name)
        if name is None:
            return None
        self._load_sources()
        if name not in self._sources:
            if not create:
                return None
            self._sources[name] = self._insert(
                'sources', {'name': name}, 'source_id',
                lambda: self._client.table('sources').select('source_id').eq('name', name).execute().data)
        return self._sources[name]

    def category_id(self, source_id: int | None, name) -> int | None:
        name = _clean(name)
        if name is None or source_id is None:
            return None
        self._load_categories()
        key = (source_id, name)
        if key not in self._categories:
            self._categories[key] = self._insert(
                'categories', {'source_id': source_id, 'name': name}, 'category_id',
                lambda: self._client.table('categories').select('category_id')
                .eq('source_id', source_id).eq('name', name).execute().data)
        return self._categories[key]

    def location_id(self, name) -> int | None:
        name = _clean(name)
        if name is None:
            return None
        self._load_locations()
        if name not in self._locations:
            self._locations[name] = self._insert(
                'locations', {'name': name}, 'location_id',
                lambda: self._client.table('locations').select('location_id').eq('name', name).execute().data)
        return self._locations[name]

    def brand_id(self, name) -> int | None:
        name = _clean(name)
        if name is None:
            return None
        self._load_brands()
        key = name.lower()
        if key not in self._brands:
            self._brands[key] = self._insert(
                'brands', {'name': name}, 'brand_id',
                lambda: self._client.table('brands').select('brand_id').ilike('name', name).execute().data)
        return self._brands[key]

    def model_id(self, brand_id: int | None, name) -> int | None:
        name = _clean(name)
        if name is None or brand_id is None:
            return None
        self._load_models()
        key = (brand_id, name.lower())
        if key not in self._models:
            self._models[key] = self._insert(
                'models', {'brand_id': brand_id, 'name': name}, 'model_id',
                lambda: self._client.table('models').select('model_id')
                .eq('brand_id', brand_id).ilike('name', name).execute().data)
        return self._models[key]


_instances: dict[int, Lookups] = {}


def get_lookups(client) -> Lookups:
    """One cache per Supabase client (i.e. per process in practice)."""
    key = id(client)
    if key not in _instances:
        _instances[key] = Lookups(client)
    return _instances[key]


def upsert_rows(client, table: str, rows: list[dict], on_conflict: str, batch: int = 500):
    """Upsert rows in groups that share the same set of keys.

    A bulk upsert sends the union of all rows' keys as its column list, so a
    key missing from one row is written as NULL for that row — e.g. a
    partial update that only sometimes carries `condition` would blank the
    condition of every other row in the same batch. Grouping by key set
    means each row only ever touches the columns it actually carries.
    """
    groups: dict[frozenset, list[dict]] = {}
    for row in rows:
        groups.setdefault(frozenset(row), []).append(row)
    for group in groups.values():
        for i in range(0, len(group), batch):
            client.table(table).upsert(group[i:i + batch], on_conflict=on_conflict).execute()
