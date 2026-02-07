"""
Custom exceptions for genimg.

This module defines all custom exceptions used throughout the application.
"""



class GenimgError(Exception):
    """Base exception for all genimg errors."""

    pass


class ValidationError(GenimgError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str = "") -> None:
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Name of the field that failed validation (optional)
        """
        self.field = field
        super().__init__(message)


class APIError(GenimgError):
    """Raised when an API call fails."""

    def __init__(self, message: str, status_code: int = 0, response: str = "") -> None:
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code (if applicable)
            response: Raw API response (if available)
        """
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class NetworkError(GenimgError):
    """Raised when a network operation fails."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """
        Initialize network error.

        Args:
            message: Error message
            original_error: The underlying exception that caused this error
        """
        self.original_error = original_error
        super().__init__(message)


class CancellationError(GenimgError):
    """Raised when an operation is cancelled by the user."""

    pass


class RequestTimeoutError(GenimgError):
    """Raised when an operation times out (e.g. request or backend call)."""

    pass


class ConfigurationError(GenimgError):
    """Raised when there is a configuration problem."""

    pass


class ImageProcessingError(GenimgError):
    """Raised when image processing fails."""

    def __init__(self, message: str, image_path: str = "") -> None:
        """
        Initialize image processing error.

        Args:
            message: Error message
            image_path: Path to the image that caused the error
        """
        self.image_path = image_path
        super().__init__(message)
