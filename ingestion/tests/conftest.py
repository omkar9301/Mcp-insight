from __future__ import annotations


class FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

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


def _matches(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        val = doc.get(key)
        if isinstance(cond, dict):
            if "$gte" in cond and not (val is not None and val >= cond["$gte"]):
                return False
            if "$lt" in cond and not (val is not None and val < cond["$lt"]):
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
