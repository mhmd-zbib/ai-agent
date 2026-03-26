"""
ScientificCalcTool — evaluates scientific formulas using numpy, scipy, and sympy.

The AI generates a Python expression formula; this tool executes it in a
restricted namespace. Variables are substituted at evaluation time.
"""

from __future__ import annotations

import math
from typing import Any

from app.modules.tools.base import BaseTool
from app.modules.tools.exceptions import ToolExecutionError, ToolValidationError
from app.shared.logging import get_logger

logger = get_logger(__name__)


class ScientificCalcTool(BaseTool):
    name = "scientific_calc"
    description = (
        "Executes scientific and mathematical formulas using numpy (np), scipy, and "
        "sympy (sp). The formula must be a Python expression string. Variable values "
        "are supplied separately and substituted at runtime. Use for physics, chemistry, "
        "statistics, biology, and any domain requiring scientific computation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "formula": {
                "type": "string",
                "description": (
                    "A Python expression using numpy (np), scipy, sympy (sp), or math. "
                    "Variable names must match the keys in 'variables'. "
                    "Examples: 'np.sqrt(v**2 + u**2)', '0.5 * m * v**2', "
                    "'sp.integrate(sp.sin(x), x)'."
                ),
            },
            "variables": {
                "type": "object",
                "description": (
                    "Dictionary mapping variable names to their numeric values. "
                    "Example: {\"m\": 5.0, \"v\": 10.0}"
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "Human-readable description of what is being calculated, "
                    "e.g. 'Kinetic energy of a 5 kg object at 10 m/s'."
                ),
            },
        },
        "required": ["formula", "variables", "description"],
    }

    # Empty builtins restrict arbitrary code execution.
    _SAFE_BUILTINS: dict[str, object] = {}

    def run(self, arguments: dict[str, Any]) -> str:
        formula = str(arguments.get("formula", "")).strip()
        raw_variables = arguments.get("variables") or {}
        description = str(arguments.get("description", ""))

        if not formula:
            raise ToolValidationError(tool_id=self.name, validation_errors=["Formula is required"])

        variables: dict[str, float] = {}
        try:
            for k, v in raw_variables.items():
                variables[str(k)] = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ToolValidationError(
                tool_id=self.name,
                validation_errors=[f"Invalid variable value: {exc}"],
            )

        try:
            import numpy as np
            import scipy
            import sympy as sp
        except ImportError as exc:
            raise ToolExecutionError(
                tool_id=self.name,
                reason=f"Missing scientific library: {exc}",
                user_message="Scientific calculation libraries are not available. Please contact support.",
            )

        namespace: dict[str, Any] = {
            "__builtins__": self._SAFE_BUILTINS,
            "np": np,
            "numpy": np,
            "scipy": scipy,
            "sp": sp,
            "sympy": sp,
            "math": math,
            **variables,
        }

        try:
            result = eval(formula, namespace)  # noqa: S307
        except ZeroDivisionError:
            raise ToolExecutionError(
                tool_id=self.name,
                reason="Division by zero in formula",
                user_message="The calculation resulted in division by zero. Please adjust your formula.",
            )
        except NameError as exc:
            raise ToolExecutionError(
                tool_id=self.name,
                reason=f"Unknown variable or function: {exc}",
                user_message=f"The formula references an unknown variable or function: {exc}",
            )
        except SyntaxError as exc:
            raise ToolExecutionError(
                tool_id=self.name,
                reason=f"Invalid formula syntax: {exc}",
                user_message=f"The formula has invalid syntax: {exc}",
            )
        except Exception as exc:
            logger.warning(
                "ScientificCalcTool: formula evaluation failed",
                extra={"formula": formula, "error": str(exc)},
            )
            raise ToolExecutionError(
                tool_id=self.name,
                reason=f"Formula evaluation failed: {exc}",
                user_message=f"I encountered an error evaluating the formula: {exc}",
            )

        lines = [f"Calculation: {description}", f"Formula: {formula}"]
        if variables:
            var_str = ", ".join(f"{k} = {v}" for k, v in variables.items())
            lines.append(f"Variables: {var_str}")
        lines.append(f"Result: {result}")

        logger.debug(
            "ScientificCalcTool: formula evaluated",
            extra={"formula": formula, "result": str(result)},
        )
        return "\n".join(lines)
