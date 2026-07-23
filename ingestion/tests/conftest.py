from __future__ import annotations


class FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, field: str, direction: int = 1) -> "FakeCursor":
        self._docs = sorted(self._docs, key=lambda d: d.get(field, 0), reverse=(direction < 0))
        return self

    def limit(self, n: int) -> "FakeCursor":
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def find(self, query: dict, *_args, **_kwargs) -> FakeCursor:
        matched = [d for d in self._docs if _matches(d, query)]
        return FakeCursor(matched)


class WritableCollection:
    """Adds find_one/update_one/insert_one on top of FakeCollection's read
    path -- used by tests that exercise mute/alert-history/key logic
    rather than pure read-only aggregation."""

    def __init__(self) -> None:
        self._docs: list[dict] = []

    def find(self, query: dict, *_args, **_kwargs) -> FakeCursor:
        return FakeCursor([d for d in self._docs if _matches(d, query)])

    async def find_one(self, query: dict) -> dict | None:
        for d in self._docs:
            if _matches(d, query):
                return d
        return None

    async def insert_one(self, doc: dict) -> None:
        self._docs.append(dict(doc))

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> "_UpdateResult":
        doc = None
        for d in self._docs:
            if _matches(d, query):
                doc = d
                break
        matched = doc is not None
        if doc is None:
            if not upsert:
                return _UpdateResult(matched_count=0)
            doc = dict(query)
            self._docs.append(doc)
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for k in update["$unset"]:
                doc.pop(k, None)
        return _UpdateResult(matched_count=1 if matched else 0)


class _UpdateResult:
    def __init__(self, matched_count: int) -> None:
        self.matched_count = matched_count


class WritableFakeDB:
    def __init__(self) -> None:
        self._collections: dict[str, WritableCollection] = {}

    def __getitem__(self, name: str) -> WritableCollection:
        if name not in self._collections:
            self._collections[name] = WritableCollection()
        return self._collections[name]


def _get_path(doc: dict, dotted_key: str):
    val = doc
    for part in dotted_key.split("."):
        if not isinstance(val, dict) or part not in val:
            return None
        val = val[part]
    return val


def _matches(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        val = _get_path(doc, key)
        if isinstance(cond, dict):
            if "$gte" in cond and not (val is not None and val >= cond["$gte"]):
                return False
            if "$lt" in cond and not (val is not None and val < cond["$lt"]):
                return False
            if "$exists" in cond and (val is not None) != cond["$exists"]:
                return False
        else:
            if val != cond:
                return False
    return True


class FakeDB:
    def __init__(self, events: list[dict]) -> None:
        self._collections = {"events": FakeCollection(events)}

    def __getitem__(self, name: str) -> FakeCollection:
        return self._collections[name]
