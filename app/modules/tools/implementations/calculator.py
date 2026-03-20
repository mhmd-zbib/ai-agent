from app.modules.tools.base import BaseTool


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Performs mathematical calculations. Evaluates arithmetic expressions and returns the result."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate (e.g., '2 + 2', '10 * 5 - 3')"
            }
        },
        "required": ["expression"]
    }

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

