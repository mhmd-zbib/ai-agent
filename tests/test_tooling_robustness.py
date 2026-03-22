from app.modules.tools.base import BaseTool
from app.modules.tools.registry import ToolRegistry


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echo back"
    parameters = {"type": "object", "properties": {"value": {"type": "string"}}}

    def run(self, arguments: dict[str, object]) -> str:
        return str(arguments.get("value", ""))


def test_tool_registry_duplicate_registration_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())

    try:
        registry.register(_EchoTool())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Expected duplicate registration to raise ValueError")


def test_tool_registry_list_tools_exposes_registered_names() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())

    assert registry.list_tools() == ["echo"]
