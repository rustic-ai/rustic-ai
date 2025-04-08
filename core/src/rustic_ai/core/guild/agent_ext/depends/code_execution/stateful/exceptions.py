class ExecutorError(Exception):
    """Base exception for code execution related errors.

    This is the parent class for all exceptions that can occur during code execution
    operations. It provides a common base for catching and handling any execution-related
    errors.

    Example:
        try:
            executor.run(code_snippet)
        except ExecutorError as e:
            print(f"Code execution failed: {e}")
    """

    pass


class ShutdownError(ExecutorError):
    """Exception raised when there is an error during executor shutdown.

    This exception indicates that something went wrong while trying to cleanly shut down
    a code executor. This could be due to failing to release resources, close connections,
    or terminate running processes.

    Example:
        try:
            executor.shutdown()
        except ShutdownError as e:
            print(f"Failed to shut down executor: {e}")
    """

    pass


class ValidationError(ExecutorError):
    """Exception raised when code validation fails.

    This exception indicates that the code snippet failed validation checks before
    execution. This could be due to unsupported programming language, security
    restrictions, or other validation rules implemented by the CodeValidator.

    Args:
        message: A description of why validation failed.

    Example:
        try:
            validator.validate(snippet)
        except ValidationError as e:
            print(f"Code validation failed: {e}")
    """

    def __init__(self, message: str):
        super().__init__(message)
