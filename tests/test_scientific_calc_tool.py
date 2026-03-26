"""Tests for ScientificCalcTool."""

from __future__ import annotations

import pytest

from app.modules.tools.implementations.scientific_calc import ScientificCalcTool
from app.modules.tools.exceptions import ToolValidationError, ToolExecutionError


@pytest.fixture()
def tool() -> ScientificCalcTool:
    return ScientificCalcTool()


# ---------------------------------------------------------------------------
# Basic arithmetic via numpy
# ---------------------------------------------------------------------------


def test_run_simple_arithmetic(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {"formula": "m * v**2 / 2", "variables": {"m": 2.0, "v": 3.0}, "description": "KE"}
    )
    assert "9.0" in result
    assert "Formula: m * v**2 / 2" in result
    assert "Calculation: KE" in result


def test_run_numpy_sqrt(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {
            "formula": "np.sqrt(x)",
            "variables": {"x": 16.0},
            "description": "Square root of 16",
        }
    )
    assert "4.0" in result


def test_run_numpy_pi_formula(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {
            "formula": "np.pi * r**2",
            "variables": {"r": 1.0},
            "description": "Area of unit circle",
        }
    )
    # pi ≈ 3.14159
    assert "3.14" in result


def test_run_math_log(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {
            "formula": "math.log(x)",
            "variables": {"x": 1.0},
            "description": "Natural log of 1",
        }
    )
    assert "0.0" in result


def test_run_no_variables(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {"formula": "np.e", "variables": {}, "description": "Euler number"}
    )
    assert "2.71" in result


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_run_empty_formula_returns_error(tool: ScientificCalcTool) -> None:
    with pytest.raises(ToolValidationError) as exc_info:
        tool.run({"formula": "", "variables": {}, "description": "nothing"})
    assert "Formula is required" in str(exc_info.value)


def test_run_zero_division_returns_error(tool: ScientificCalcTool) -> None:
    with pytest.raises(ToolExecutionError) as exc_info:
        tool.run(
            {"formula": "1 / x", "variables": {"x": 0.0}, "description": "div by zero"}
        )
    assert "division by zero" in str(exc_info.value).lower()


def test_run_unknown_variable_returns_error(tool: ScientificCalcTool) -> None:
    with pytest.raises(ToolExecutionError) as exc_info:
        tool.run(
            {
                "formula": "unknown_var + 1",
                "variables": {},
                "description": "bad variable",
            }
        )
    assert "unknown" in str(exc_info.value).lower()


def test_run_invalid_syntax_returns_error(tool: ScientificCalcTool) -> None:
    with pytest.raises(ToolExecutionError) as exc_info:
        tool.run(
            {"formula": "!!!bad syntax!!!", "variables": {}, "description": "syntax error"}
        )
    assert "syntax" in str(exc_info.value).lower()


def test_run_invalid_variable_value_returns_error(tool: ScientificCalcTool) -> None:
    with pytest.raises(ToolValidationError) as exc_info:
        tool.run(
            {
                "formula": "x + 1",
                "variables": {"x": "not_a_number"},
                "description": "bad value",
            }
        )
    assert "Invalid variable value" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_run_output_contains_variables_block(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {
            "formula": "a + b",
            "variables": {"a": 1.0, "b": 2.0},
            "description": "addition",
        }
    )
    assert "Variables:" in result
    assert "a = 1.0" in result
    assert "b = 2.0" in result


def test_run_output_result_line_present(tool: ScientificCalcTool) -> None:
    result = tool.run(
        {"formula": "5 + 3", "variables": {}, "description": "simple add"}
    )
    assert "Result:" in result


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_to_openai_tool_has_correct_name(tool: ScientificCalcTool) -> None:
    schema = tool.to_openai_tool()
    assert schema["function"]["name"] == "scientific_calc"


def test_to_openai_tool_required_params(tool: ScientificCalcTool) -> None:
    schema = tool.to_openai_tool()
    required = schema["function"]["parameters"]["required"]
    assert "formula" in required
    assert "variables" in required
    assert "description" in required
