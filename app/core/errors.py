"""Application-level exceptions.

Every error a user can trigger is mapped to one of these classes. The API layer
turns them into clean JSON responses with a human-readable message, so internal
stack traces never reach the browser.
"""


class CoachError(Exception):
    """Base class for expected, user-facing errors."""

    status_code: int = 400
    error_code: str = "coach_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DocumentError(CoachError):
    """A document could not be read, or its content is unusable."""

    status_code = 422
    error_code = "document_error"


class UnsupportedFormatError(DocumentError):
    status_code = 415
    error_code = "unsupported_format"


class SessionNotFoundError(CoachError):
    status_code = 404
    error_code = "session_not_found"


class EmbeddingError(CoachError):
    status_code = 503
    error_code = "embedding_error"


class RetrievalError(CoachError):
    status_code = 500
    error_code = "retrieval_error"


class LLMError(CoachError):
    """The LLM provider was unreachable, timed out or returned unusable output."""

    status_code = 502
    error_code = "llm_error"
