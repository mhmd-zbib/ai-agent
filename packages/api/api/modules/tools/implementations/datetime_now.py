from __future__ import annotations

from datetime import UTC, datetime

from api.modules.tools.base import BaseTool


class DateTimeNowTool(BaseTool):
    name = "datetime_now"
    description = "Returns the current date and time in UTC or local timezone."
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone output mode. Supported values: 'utc' or 'local'.",
                "enum": ["utc", "local"],
                "default": "utc",
            }
        },
        "required": [],
    }

    def run(self, arguments: dict[str, object]) -> str:
        timezone_mode = str(arguments.get("timezone", "utc")).strip().lower()
        if timezone_mode == "local":
            now = datetime.now().astimezone()
            return f"Local time: {now.isoformat()}"

        now_utc = datetime.now(UTC)
        return f"UTC time: {now_utc.isoformat()}"
