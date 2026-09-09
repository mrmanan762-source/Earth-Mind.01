from modules.database.sqlite_db import SQLiteDatabaseService
from modules.database.db_module import SQLiteDatabaseModule
from core.schemas.application import ApplicationRequest

def test_sqlite_db_service():
    db = SQLiteDatabaseService(":memory:")
    db.connect()

    db.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    db.execute("INSERT INTO test_table (name) VALUES (?)", ("EarthMind",))

    row = db.fetch_one("SELECT * FROM test_table WHERE name = ?", ("EarthMind",))
    assert row is not None
    assert row["name"] == "EarthMind"

    rows = db.fetch_all("SELECT * FROM test_table")
    assert len(rows) == 1

    db.disconnect()

def test_sqlite_db_module():
    db_module = SQLiteDatabaseModule(":memory:")
    db_module.initialize()

    req_create = ApplicationRequest(
        request_id="db-1",
        source="test",
        operation="execute",
        payload={"query": "CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT)"}
    )
    resp_create = db_module.handle(req_create)
    assert resp_create.status == "SUCCESS"

    req_insert = ApplicationRequest(
        request_id="db-2",
        source="test",
        operation="execute",
        payload={"query": "INSERT INTO items (title) VALUES (?)", "params": ("item_1",)}
    )
    resp_insert = db_module.handle(req_insert)
    assert resp_insert.status == "SUCCESS"

    req_fetch = ApplicationRequest(
        request_id="db-3",
        source="test",
        operation="fetch_all",
        payload={"query": "SELECT * FROM items"}
    )
    resp_fetch = db_module.handle(req_fetch)
    assert resp_fetch.status == "SUCCESS"
    assert len(resp_fetch.response) == 1
    assert resp_fetch.response[0]["title"] == "item_1"

    db_module.shutdown()
