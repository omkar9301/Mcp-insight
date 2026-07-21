import pytest

from app import keys
from .conftest import FakeDB


class FakeKeysCollection:
    """Extends the read-only FakeCollection with the update/find_one/unset
    behavior keys.py needs -- kept local to this test file since it's the
    only place that needs a *writable* fake collection."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    async def find_one(self, query: dict) -> dict | None:
        return self._docs.get(query["server_id"])

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        server_id = query["server_id"]
        doc = self._docs.get(server_id, {"server_id": server_id})
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for k in update["$unset"]:
                doc.pop(k, None)
        if "$setOnInsert" in update and server_id not in self._docs:
            doc.update(update["$setOnInsert"])
        self._docs[server_id] = doc


class FakeKeysDB:
    def __init__(self) -> None:
        self._servers = FakeKeysCollection()

    def __getitem__(self, name: str):
        assert name == "servers"
        return self._servers


@pytest.mark.asyncio
async def test_set_and_verify_key_roundtrip(monkeypatch):
    db = FakeKeysDB()
    monkeypatch.setattr(keys, "get_db", lambda: db)

    plaintext = await keys.set_server_key("srv-1")
    assert plaintext.startswith("mcpi_")
    assert await keys.verify_server_key("srv-1", plaintext) is True


@pytest.mark.asyncio
async def test_verify_rejects_wrong_key(monkeypatch):
    db = FakeKeysDB()
    monkeypatch.setattr(keys, "get_db", lambda: db)

    await keys.set_server_key("srv-1")
    assert await keys.verify_server_key("srv-1", "wrong-key") is False


@pytest.mark.asyncio
async def test_verify_rejects_unknown_server(monkeypatch):
    db = FakeKeysDB()
    monkeypatch.setattr(keys, "get_db", lambda: db)
    assert await keys.verify_server_key("never-provisioned", "anything") is False


@pytest.mark.asyncio
async def test_rotate_invalidates_previous_key(monkeypatch):
    db = FakeKeysDB()
    monkeypatch.setattr(keys, "get_db", lambda: db)

    old_key = await keys.set_server_key("srv-1")
    new_key = await keys.set_server_key("srv-1")

    assert old_key != new_key
    assert await keys.verify_server_key("srv-1", old_key) is False
    assert await keys.verify_server_key("srv-1", new_key) is True


@pytest.mark.asyncio
async def test_revoke_removes_key(monkeypatch):
    db = FakeKeysDB()
    monkeypatch.setattr(keys, "get_db", lambda: db)

    plaintext = await keys.set_server_key("srv-1")
    await keys.revoke_server_key("srv-1")
    assert await keys.verify_server_key("srv-1", plaintext) is False


@pytest.mark.asyncio
async def test_keys_scoped_per_server(monkeypatch):
    db = FakeKeysDB()
    monkeypatch.setattr(keys, "get_db", lambda: db)

    key_a = await keys.set_server_key("srv-a")
    await keys.set_server_key("srv-b")

    assert await keys.verify_server_key("srv-b", key_a) is False
