"""
Mock Database Tool - Demonstrates multiple parameter types and complex return formats.

This tool showcases:
- Multiple parameter types (string, integer)
- Input sanitization for SQL injection prevention
- Pagination handling (limit/offset)
- Structured data return format
- Comprehensive error handling
"""

import json
import re
from typing import Any

from ..base import BaseTool
from common.core.log_config import get_logger

logger = get_logger(__name__)


class MockDatabaseTool(BaseTool):
    """
    Mock database query tool that simulates SQL queries against a fake dataset.

    This tool demonstrates:
    - Multiple parameter types (string, integers)
    - SQL injection prevention through input sanitization
    - Pagination with limit/offset parameters
    - Complex structured return format
    - Metadata in responses (total count, query info)

    Examples:
        >>> tool = MockDatabaseTool()
        >>> result = tool.run({"query": "SELECT * FROM users"})
        >>> # Returns paginated mock data with 10 results

        >>> result = tool.run({"query": "SELECT * FROM products", "limit": 5, "offset": 10})
        >>> # Returns 5 results starting from offset 10

        >>> result = tool.run({"query": "SELECT * FROM users; DROP TABLE users;"})
        >>> # Returns error - potential SQL injection detected
    """

    name = "mock_database"
    description = (
        "Executes mock SQL queries against a simulated database. "
        "Returns structured results with pagination support. "
        "Includes SQL injection prevention and query validation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The SQL query to execute (e.g., 'SELECT * FROM users WHERE status = active')",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 10, max: 100)",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
            "offset": {
                "type": "integer",
                "description": "Number of results to skip for pagination (default: 0)",
                "default": 0,
                "minimum": 0,
            },
        },
        "required": ["query"],
    }

    # Mock database tables
    MOCK_TABLES = {
        "users": ["id", "name", "email", "status", "created_at"],
        "products": ["id", "name", "price", "category", "stock"],
        "orders": ["id", "user_id", "product_id", "quantity", "total", "order_date"],
    }

    # SQL injection patterns to detect
    SUSPICIOUS_PATTERNS = [
        r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE)",
        r"--",
        r"/\*.*\*/",
        r"UNION.*SELECT",
        r"exec\s*\(",
        r"script\s*>",
    ]

    def run(self, arguments: dict[str, Any]) -> str:
        """
        Execute the mock database query.

        Args:
            arguments: Dictionary containing:
                - query (str): SQL query to execute
                - limit (int, optional): Max results to return (default: 10)
                - offset (int, optional): Results to skip (default: 0)

        Returns:
            str: JSON-formatted string with query results or error message
        """
        logger.info(f"MockDatabaseTool called with arguments: {arguments}")

        # Extract and validate parameters
        query = arguments.get("query", "").strip()
        limit = arguments.get("limit", 10)
        offset = arguments.get("offset", 0)

        # Validate query parameter
        if not query:
            error_msg = "Error: Query parameter is required and cannot be empty"
            logger.warning(error_msg)
            return json.dumps({"error": error_msg}, indent=2)

        # Validate limit parameter
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            error_msg = (
                f"Error: Limit must be an integer between 1 and 100, got: {limit}"
            )
            logger.warning(error_msg)
            return json.dumps({"error": error_msg}, indent=2)

        # Validate offset parameter
        if not isinstance(offset, int) or offset < 0:
            error_msg = f"Error: Offset must be a non-negative integer, got: {offset}"
            logger.warning(error_msg)
            return json.dumps({"error": error_msg}, indent=2)

        # Check for SQL injection attempts
        sanitization_result = self._sanitize_query(query)
        if not sanitization_result["safe"]:
            error_msg = f"Error: Potential SQL injection detected - {sanitization_result['reason']}"
            logger.warning(f"{error_msg}. Query: {query}")
            return json.dumps(
                {
                    "error": error_msg,
                    "blocked_query": query,
                    "security_note": "This tool blocks potentially dangerous SQL patterns",
                },
                indent=2,
            )

        # Parse and validate table name
        table_name = self._extract_table_name(query)
        if not table_name:
            error_msg = "Error: Could not parse table name from query"
            logger.warning(f"{error_msg}. Query: {query}")
            return json.dumps({"error": error_msg}, indent=2)

        if table_name not in self.MOCK_TABLES:
            error_msg = f"Error: Table '{table_name}' not found"
            logger.warning(
                f"{error_msg}. Available tables: {list(self.MOCK_TABLES.keys())}"
            )
            return json.dumps(
                {"error": error_msg, "available_tables": list(self.MOCK_TABLES.keys())},
                indent=2,
            )

        # Generate mock results
        results = self._generate_mock_results(table_name, limit, offset)
        logger.info(
            f"Generated {len(results['data'])} mock results for table {table_name}"
        )

        return json.dumps(results, indent=2)

    def _sanitize_query(self, query: str) -> dict[str, Any]:
        """
        Check query for SQL injection patterns.

        Args:
            query: SQL query string to validate

        Returns:
            Dictionary with 'safe' boolean and optional 'reason' for blocked queries
        """
        query_upper = query.upper()

        # Check for suspicious patterns
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, query_upper, re.IGNORECASE):
                return {
                    "safe": False,
                    "reason": f"Dangerous pattern detected: {pattern}",
                }

        # Check for multiple statements (simple check)
        if query.count(";") > 1:
            return {
                "safe": False,
                "reason": "Multiple statements detected (potential injection)",
            }

        return {"safe": True}

    def _extract_table_name(self, query: str) -> str | None:
        """
        Extract table name from SQL query.

        Args:
            query: SQL query string

        Returns:
            Table name if found, None otherwise
        """
        # Simple regex to extract table name from SELECT statements
        match = re.search(r"FROM\s+(\w+)", query, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def _generate_mock_results(
        self, table_name: str, limit: int, offset: int
    ) -> dict[str, Any]:
        """
        Generate mock database results for a table.

        Args:
            table_name: Name of the table to query
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Dictionary with results, metadata, and pagination info
        """
        columns = self.MOCK_TABLES[table_name]
        total_records = 42  # Mock total count

        # Generate mock rows
        data = []
        for i in range(offset, min(offset + limit, total_records)):
            row = {}
            for col in columns:
                row[col] = self._generate_mock_value(col, i)
            data.append(row)

        return {
            "query_info": {
                "table": table_name,
                "columns": columns,
                "limit": limit,
                "offset": offset,
            },
            "pagination": {
                "total_records": total_records,
                "returned_records": len(data),
                "has_more": offset + limit < total_records,
                "next_offset": offset + limit
                if offset + limit < total_records
                else None,
            },
            "data": data,
            "execution_time_ms": 23,
        }

    def _generate_mock_value(self, column: str, row_index: int) -> Any:
        """
        Generate a mock value for a database column.

        Args:
            column: Column name
            row_index: Row index for unique values

        Returns:
            Mock value appropriate for the column
        """
        if column == "id":
            return row_index + 1
        elif column == "name":
            return f"Item {row_index + 1}"
        elif column == "email":
            return f"user{row_index + 1}@example.com"
        elif column == "status":
            statuses = ["active", "inactive", "pending"]
            return statuses[row_index % len(statuses)]
        elif column == "price":
            return round(19.99 + (row_index * 5.5), 2)
        elif column == "quantity":
            return (row_index % 10) + 1
        elif column == "stock":
            return (row_index % 50) + 10
        elif column in ["created_at", "order_date"]:
            return f"2024-01-{(row_index % 28) + 1:02d}T10:00:00Z"
        elif "id" in column:  # Foreign keys like user_id, product_id
            return (row_index % 20) + 1
        else:
            return f"value_{row_index + 1}"
