from app.modules.tools.base import BaseTool


class CalculatorTool(BaseTool):
    name = "calculator"

    def run(self, arguments: dict[str, object]) -> str:
        expression = str(arguments.get("expression", ""))
        if not expression:
            return "No expression provided."
        try:
            # Intentionally keep a restricted eval context for simple arithmetic.
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
            return str(result)
        except Exception:
            return "Invalid expression."

