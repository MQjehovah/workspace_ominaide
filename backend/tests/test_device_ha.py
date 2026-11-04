import json


async def test_ha_list_entities_tool(monkeypatch):
    from plugins.device.backend import tools

    async def fake_list_entities(domain=None, query=None, limit=80):
        return {
            "ok": True,
            "total": 2,
            "matched": 1,
            "domains": {"light": 1, "sensor": 1},
            "entities": [
                {
                    "entity_id": "light.philips_lamp",
                    "name": "台灯",
                    "state": "off",
                    "domain": "light",
                }
            ],
        }

    monkeypatch.setattr(tools.ha, "list_entities", fake_list_entities)
    result = await tools.ha_list_entities(1, {"query": "台灯"})
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["entities"][0]["entity_id"] == "light.philips_lamp"


async def test_ha_toggle_rejects_missing_entity(monkeypatch):
    from plugins.device.backend import tools

    monkeypatch.setattr(tools.ha, "ha_configured", lambda: True)

    async def fake_get_state(entity_id):
        return None

    monkeypatch.setattr(tools.ha, "get_state", fake_get_state)
    result = await tools.ha_toggle(1, {"entity_id": "light.desk_lamp"})
    assert result.isError
    assert "ha_list_entities" in result.content[0].text


async def test_ha_toggle_returns_friendly_name(monkeypatch):
    from plugins.device.backend import tools

    monkeypatch.setattr(tools.ha, "ha_configured", lambda: True)

    async def fake_get_state(entity_id):
        return {
            "entity_id": entity_id,
            "state": "off",
            "attributes": {"friendly_name": "台灯"},
        }

    async def fake_call_service(domain, service, entity_id=None, data=None):
        return {"ok": True, "detail": "ok", "changed": 1}

    monkeypatch.setattr(tools.ha, "get_state", fake_get_state)
    monkeypatch.setattr(tools.ha, "call_service", fake_call_service)
    result = await tools.ha_toggle(1, {"entity_id": "light.philips_lamp"})
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["friendly_name"] == "台灯"
    assert payload["state_before"] == "off"
