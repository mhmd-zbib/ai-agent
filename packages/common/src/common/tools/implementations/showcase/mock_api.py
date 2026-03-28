"""
Mock API Tool - Demonstrates object parameters, nested validation, and error states.

This tool showcases:
- Object parameter handling
- Nested parameter validation
- HTTP method validation
- Status code simulation
- Error state handling
- Retry logic examples
- Timeout simulation
"""

import json
import random
from typing import Any

from ..base import BaseTool
from common.core.log_config import get_logger

logger = get_logger(__name__)


class MockAPITool(BaseTool):
    """
    Mock API request tool that simulates HTTP requests to external APIs.

    This tool demonstrates:
    - Object parameters for complex nested data
    - HTTP method validation (GET, POST, PUT, DELETE)
    - Request header and body handling
    - HTTP status code simulation
    - Error states (4xx, 5xx responses)
    - Timeout simulation
    - Retry logic examples

    Examples:
        >>> tool = MockAPITool()
        >>> result = tool.run({
        ...     "endpoint": "/users",
        ...     "method": "GET"
        ... })
        >>> # Returns 200 response with mock user data

        >>> result = tool.run({
        ...     "endpoint": "/users",
        ...     "method": "POST",
        ...     "body": {"name": "John", "email": "john@example.com"}
        ... })
        >>> # Returns 201 response indicating resource created

        >>> result = tool.run({
        ...     "endpoint": "/slow-endpoint",
        ...     "method": "GET",
        ...     "headers": {"timeout": "1"}
        ... })
        >>> # May return timeout error
    """

    name = "mock_api"
    description = (
        "Makes mock HTTP API requests to simulated endpoints. "
        "Supports GET, POST, PUT, DELETE methods with headers and body. "
        "Returns realistic API responses with status codes and data."
    )
    parameters = {
        "type": "object",
        "properties": {
            "endpoint": {
                "type": "string",
                "description": "The API endpoint path to call (e.g., '/users', '/api/products/123')",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP method to use for the request",
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs (e.g., {'Authorization': 'Bearer token'})",
                "additionalProperties": {"type": "string"},
            },
            "body": {
                "type": "object",
                "description": "Optional request body for POST/PUT requests (as JSON object)",
            },
        },
        "required": ["endpoint"],
    }

    # Mock API endpoints with their behaviors
    ENDPOINT_BEHAVIORS = {
        "/users": {
            "GET": {"status": 200, "data_type": "list"},
            "POST": {"status": 201, "data_type": "create"},
        },
        "/products": {
            "GET": {"status": 200, "data_type": "list"},
            "POST": {"status": 201, "data_type": "create"},
        },
        "/orders": {
            "GET": {"status": 200, "data_type": "list"},
            "POST": {"status": 201, "data_type": "create"},
        },
        "/error-endpoint": {
            "GET": {"status": 500, "data_type": "error"},
        },
        "/auth-required": {
            "GET": {"status": 401, "data_type": "error"},
        },
        "/not-found": {
            "GET": {"status": 404, "data_type": "error"},
        },
        "/slow-endpoint": {
            "GET": {"status": 200, "data_type": "slow", "delay": 3},
        },
    }

    # Valid HTTP methods
    VALID_METHODS = ["GET", "POST", "PUT", "DELETE"]

    def run(self, arguments: dict[str, Any]) -> str:
        """
        Execute the mock API request.

        Args:
            arguments: Dictionary containing:
                - endpoint (str): API endpoint path
                - method (str, optional): HTTP method (default: "GET")
                - headers (dict, optional): HTTP headers
                - body (dict, optional): Request body for POST/PUT

        Returns:
            str: JSON-formatted string with API response or error
        """
        logger.info(f"MockAPITool called with arguments: {arguments}")

        # Extract parameters
        endpoint = arguments.get("endpoint", "").strip()
        method = arguments.get("method", "GET").upper()
        headers = arguments.get("headers", {})
        body = arguments.get("body")

        # Validate endpoint
        if not endpoint:
            error_msg = "Error: Endpoint parameter is required and cannot be empty"
            logger.warning(error_msg)
            return self._format_error_response(400, error_msg)

        # Validate method
        if method not in self.VALID_METHODS:
            error_msg = f"Error: Invalid HTTP method '{method}'. Must be one of: {', '.join(self.VALID_METHODS)}"
            logger.warning(error_msg)
            return self._format_error_response(400, error_msg)

        # Validate headers if provided
        if headers and not isinstance(headers, dict):
            error_msg = "Error: Headers must be a dictionary/object"
            logger.warning(error_msg)
            return self._format_error_response(400, error_msg)

        # Validate body if provided
        if body and not isinstance(body, dict):
            error_msg = "Error: Body must be a dictionary/object"
            logger.warning(error_msg)
            return self._format_error_response(400, error_msg)

        # Check if body is provided for POST/PUT (warning, not error)
        if method in ["POST", "PUT"] and not body:
            logger.warning(f"{method} request to {endpoint} without body")

        # Simulate timeout check
        timeout_result = self._check_timeout(headers)
        if timeout_result:
            logger.warning(f"Request to {endpoint} timed out")
            return timeout_result

        # Simulate retry logic for specific endpoints
        retry_result = self._simulate_retry_logic(endpoint, method)
        if retry_result:
            return retry_result

        # Generate mock API response
        response = self._generate_mock_response(endpoint, method, headers, body)
        logger.info(
            f"Mock API response: {response['status_code']} for {method} {endpoint}"
        )

        return json.dumps(response, indent=2)

    def _check_timeout(self, headers: dict[str, Any]) -> str | None:
        """
        Simulate timeout based on headers.

        Args:
            headers: Request headers

        Returns:
            Error response if timeout occurs, None otherwise
        """
        # Check if timeout header is set
        timeout = headers.get("timeout") or headers.get("Timeout")
        if timeout:
            try:
                timeout_seconds = int(timeout)
                # Simulate random timeout 30% of the time
                if random.random() < 0.3:
                    return self._format_error_response(
                        408,
                        f"Request timeout after {timeout_seconds} seconds",
                        {"retry_after": 5},
                    )
            except (ValueError, TypeError):
                pass
        return None

    def _simulate_retry_logic(self, endpoint: str, method: str) -> str | None:
        """
        Simulate retry logic for flaky endpoints.

        Args:
            endpoint: API endpoint
            method: HTTP method

        Returns:
            Success response after retries or None
        """
        # Simulate flaky endpoint that needs retries
        if "flaky" in endpoint.lower():
            logger.info(f"Flaky endpoint detected: {endpoint}")
            # Simulate 2 retries
            for attempt in range(1, 4):
                logger.info(f"Retry attempt {attempt}/3 for {endpoint}")
                # 70% chance of success on each retry
                if random.random() < 0.7:
                    return json.dumps(
                        {
                            "status_code": 200,
                            "message": f"Success after {attempt} retry(s)",
                            "data": {"endpoint": endpoint, "retries": attempt},
                            "headers": {"X-Retry-Count": str(attempt)},
                        },
                        indent=2,
                    )

            # All retries failed
            return self._format_error_response(
                503, "Service unavailable after 3 retry attempts", {"retry_after": 60}
            )

        return None

    def _generate_mock_response(
        self,
        endpoint: str,
        method: str,
        headers: dict[str, Any],
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Generate a mock API response.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            headers: Request headers
            body: Request body

        Returns:
            Dictionary with status code, headers, and data
        """
        # Normalize endpoint for matching
        endpoint_normalized = endpoint.rstrip("/")

        # Check if we have a defined behavior for this endpoint
        behavior = None
        if endpoint_normalized in self.ENDPOINT_BEHAVIORS:
            endpoint_config = self.ENDPOINT_BEHAVIORS[endpoint_normalized]
            behavior = endpoint_config.get(method)

        # Check for auth requirement
        if "auth" in headers or "Authorization" in headers:
            auth_valid = self._validate_auth(headers)
            if not auth_valid:
                return {
                    "status_code": 401,
                    "error": "Unauthorized",
                    "message": "Invalid or missing authentication token",
                    "headers": {"WWW-Authenticate": "Bearer"},
                }

        # Generate response based on behavior
        if behavior:
            return self._generate_response_from_behavior(
                behavior, endpoint, method, body
            )

        # Default: resource-based response
        return self._generate_default_response(endpoint, method, body)

    def _validate_auth(self, headers: dict[str, Any]) -> bool:
        """
        Validate authentication headers.

        Args:
            headers: Request headers

        Returns:
            True if auth is valid, False otherwise
        """
        auth = headers.get("Authorization") or headers.get("auth")
        if auth and isinstance(auth, str):
            # Accept any Bearer token that's at least 10 chars
            if auth.startswith("Bearer ") and len(auth) > 17:
                return True
        return False

    def _generate_response_from_behavior(
        self,
        behavior: dict[str, Any],
        endpoint: str,
        method: str,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Generate response based on defined behavior.

        Args:
            behavior: Endpoint behavior configuration
            endpoint: API endpoint
            method: HTTP method
            body: Request body

        Returns:
            Response dictionary
        """
        status = behavior["status"]
        data_type = behavior["data_type"]

        if data_type == "error":
            return {
                "status_code": status,
                "error": self._get_error_name(status),
                "message": self._get_error_message(status),
                "headers": {"Content-Type": "application/json"},
            }

        if data_type == "list":
            return {
                "status_code": status,
                "data": self._generate_list_data(endpoint),
                "pagination": {"page": 1, "per_page": 10, "total": 42},
                "headers": {"Content-Type": "application/json"},
            }

        if data_type == "create":
            return {
                "status_code": status,
                "data": {
                    "id": random.randint(1000, 9999),
                    **(body or {}),
                    "created_at": "2024-01-15T12:00:00Z",
                },
                "message": "Resource created successfully",
                "headers": {
                    "Content-Type": "application/json",
                    "Location": f"{endpoint}/1234",
                },
            }

        return {"status_code": status, "data": {}}

    def _generate_default_response(
        self, endpoint: str, method: str, body: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        Generate default response for undefined endpoints.

        Args:
            endpoint: API endpoint
            method: HTTP method
            body: Request body

        Returns:
            Response dictionary
        """
        if method == "GET":
            return {
                "status_code": 200,
                "data": {"endpoint": endpoint, "method": method},
                "headers": {"Content-Type": "application/json"},
            }
        elif method == "POST":
            return {
                "status_code": 201,
                "data": {
                    "id": random.randint(1000, 9999),
                    **(body or {}),
                    "created_at": "2024-01-15T12:00:00Z",
                },
                "headers": {"Content-Type": "application/json"},
            }
        elif method in ["PUT", "DELETE"]:
            return {
                "status_code": 200 if method == "PUT" else 204,
                "message": f"Resource {method.lower()}d successfully",
                "headers": {"Content-Type": "application/json"},
            }

        return {"status_code": 200, "data": {}}

    def _generate_list_data(self, endpoint: str) -> list[dict[str, Any]]:
        """
        Generate mock list data based on endpoint.

        Args:
            endpoint: API endpoint

        Returns:
            List of mock items
        """
        if "users" in endpoint:
            return [
                {"id": i, "name": f"User {i}", "email": f"user{i}@example.com"}
                for i in range(1, 6)
            ]
        elif "products" in endpoint:
            return [
                {"id": i, "name": f"Product {i}", "price": 19.99 + i}
                for i in range(1, 6)
            ]
        elif "orders" in endpoint:
            return [
                {"id": i, "user_id": i, "total": 99.99 + i, "status": "completed"}
                for i in range(1, 6)
            ]

        return [{"id": i, "data": f"Item {i}"} for i in range(1, 6)]

    def _get_error_name(self, status_code: int) -> str:
        """Get error name for status code."""
        error_names = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
            503: "Service Unavailable",
        }
        return error_names.get(status_code, "Error")

    def _get_error_message(self, status_code: int) -> str:
        """Get error message for status code."""
        error_messages = {
            400: "The request was malformed or invalid",
            401: "Authentication is required to access this resource",
            403: "You don't have permission to access this resource",
            404: "The requested resource was not found",
            500: "An internal server error occurred",
            503: "The service is temporarily unavailable",
        }
        return error_messages.get(status_code, "An error occurred")

    def _format_error_response(
        self, status_code: int, message: str, extra: dict[str, Any] | None = None
    ) -> str:
        """
        Format an error response.

        Args:
            status_code: HTTP status code
            message: Error message
            extra: Additional fields to include

        Returns:
            JSON-formatted error response
        """
        response = {
            "status_code": status_code,
            "error": self._get_error_name(status_code),
            "message": message,
            "headers": {"Content-Type": "application/json"},
        }
        if extra:
            response.update(extra)

        return json.dumps(response, indent=2)
