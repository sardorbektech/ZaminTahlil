import json
import pytest

from app.mcp_server import mcp_server


@pytest.mark.asyncio
async def test_mcp_server_tools_registered() -> None:
    tools = mcp_server._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "list_fields" in tool_names
    assert "get_field_details" in tool_names
    assert "get_field_problem_zones" in tool_names
    assert "predict_crop_yield" in tool_names
    assert "get_agronomic_recommendation" in tool_names
    assert "ask_ai_agronomist" in tool_names


@pytest.mark.asyncio
async def test_mcp_call_list_fields() -> None:
    result = await mcp_server.call_tool("list_fields", {})
    assert not result.is_error
    assert len(result.content) > 0
    raw_text = result.content[0].text
    parsed = json.loads(raw_text)
    assert isinstance(parsed, list)


@pytest.mark.asyncio
async def test_mcp_call_problem_zones(tmp_path) -> None:
    # First get or register a field to test
    fields_res = await mcp_server.call_tool("list_fields", {})
    fields = json.loads(fields_res.content[0].text)
    if fields:
        field_id = fields[0]["id"]
        res = await mcp_server.call_tool("get_field_problem_zones", {"field_id": field_id})
        assert not res.is_error
        data = json.loads(res.content[0].text)
        assert "field_id" in data
        assert "summary_uz" in data
