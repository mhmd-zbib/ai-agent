import ast
import operator

from app.modules.tools.base import BaseTool


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Performs mathematical calculations. Evaluates arithmetic expressions and returns the result."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate (e.g., '2 + 2', '10 * 5 - 3')",
            }
        },
        "required": ["expression"],
    }

    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def run(self, arguments: dict[str, object]) -> str:
        expression = str(arguments.get("expression", ""))
        if not expression:
            return "Error: No expression provided."

        try:
            result = self._safe_eval(expression)
            return str(result)
        except (SyntaxError, ValueError) as e:
            return f"Error: Invalid expression - {str(e)}"
        except ZeroDivisionError:
            return "Error: Division by zero."
        except Exception as e:
            return f"Error: Could not evaluate expression - {str(e)}"

    def _safe_eval(self, expression: str) -> float | int:
        """Safely evaluate a mathematical expression using AST parsing."""
        try:
            node = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid syntax: {e}")

        return self._eval_node(node.body)

    def _eval_node(self, node: ast.AST) -> float | int:
        """Recursively evaluate an AST node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")

        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self.SAFE_OPERATORS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

            operand = self._eval_node(node.operand)
            return self.SAFE_OPERATORS[op_type](operand)

        else:
            raise ValueError(f"Unsupported expression type: {type(node).__name__}")
