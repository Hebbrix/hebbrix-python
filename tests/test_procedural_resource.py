import pytest
from hebbrix.resources import ProceduralResource
from hebbrix.sync_client import SyncProceduralResource


class RecordingClient:
    def __init__(self):
        self.calls = []

    async def post(self, path, **kwargs):
        self.calls.append(("POST", path, kwargs))
        if path == "/v1/procedures":
            return {"status": "success", "procedure_id": "procedure-1"}
        if path.endswith("/execute"):
            return {"execution_result": {"output": "recovered"}}
        return {"status": "success"}

    async def get(self, path, **kwargs):
        self.calls.append(("GET", path, kwargs))
        return {"procedures": []}

    async def patch(self, path, **kwargs):
        self.calls.append(("PATCH", path, kwargs))
        return {
            "status": "success",
            "procedure": {"id": "procedure-1", "name": "updated"},
        }

    async def delete(self, path, **kwargs):
        self.calls.append(("DELETE", path, kwargs))
        return {}


@pytest.mark.asyncio
async def test_procedure_lifecycle_matches_canonical_rest_contract():
    client = RecordingClient()
    resource = ProceduralResource(client)

    created = await resource.create(
        name="restart proxy",
        description="Recover the query proxy",
        trigger_condition="proxy unavailable",
        action_sequence=["recycle proxy once"],
        metadata={"owner": "on-call"},
    )
    assert await resource.list() == []
    executed = await resource.execute("procedure-1", {"incident": "INC-1"})
    updated = await resource.update(
        "procedure-1",
        trigger_condition="proxy unhealthy",
        action_sequence=["page on-call", "recycle proxy once"],
    )
    await resource.delete("procedure-1")
    assert created["id"] == "procedure-1"
    assert executed == {"output": "recovered"}
    assert updated == {"id": "procedure-1", "name": "updated"}

    assert [(method, path) for method, path, _ in client.calls] == [
        ("POST", "/v1/procedures"),
        ("GET", "/v1/procedures"),
        ("POST", "/v1/procedures/procedure-1/execute"),
        ("PATCH", "/v1/procedures/procedure-1"),
        ("DELETE", "/v1/procedures/procedure-1"),
    ]
    create = client.calls[0][2]["json"]
    assert create["condition"] == {"expression": "proxy unavailable"}
    assert create["action"] == {"steps": ["recycle proxy once"]}
    assert create["parameters"] == {"owner": "on-call"}
    assert client.calls[2][2]["json"] == {"input_state": {"incident": "INC-1"}}
    update = client.calls[3][2]["json"]
    assert update["condition"] == {"expression": "proxy unhealthy"}
    assert update["action"] == {"steps": ["page on-call", "recycle proxy once"]}


class SyncRecordingClient:
    def __init__(self):
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append(("POST", path, kwargs))
        if path == "/v1/procedures":
            return {"procedure_id": "procedure-1"}
        if path.endswith("/execute"):
            return {"execution_result": {"output": "recovered"}}
        return {}

    def get(self, path, **kwargs):
        self.calls.append(("GET", path, kwargs))
        return {"procedures": []}

    def patch(self, path, **kwargs):
        self.calls.append(("PATCH", path, kwargs))
        return {"procedure": {"id": "procedure-1", "name": "updated"}}

    def delete(self, path, **kwargs):
        self.calls.append(("DELETE", path, kwargs))
        return None


def test_sync_procedure_lifecycle_matches_canonical_rest_contract():
    client = SyncRecordingClient()
    resource = SyncProceduralResource(client)

    created = resource.create(
        name="restart proxy",
        description="Recover the query proxy",
        trigger_condition="proxy unavailable",
        action_sequence=["recycle proxy once"],
    )
    assert resource.list() == []
    assert resource.execute("procedure-1") == {"output": "recovered"}
    assert resource.update("procedure-1", name="updated")["name"] == "updated"
    assert resource.delete("procedure-1") is None
    assert created["id"] == "procedure-1"
    assert [(method, path) for method, path, _ in client.calls] == [
        ("POST", "/v1/procedures"),
        ("GET", "/v1/procedures"),
        ("POST", "/v1/procedures/procedure-1/execute"),
        ("PATCH", "/v1/procedures/procedure-1"),
        ("DELETE", "/v1/procedures/procedure-1"),
    ]
