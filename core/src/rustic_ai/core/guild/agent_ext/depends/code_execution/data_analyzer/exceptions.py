"""Custom exceptions for the data analyzer module."""


class DataAnalyzerError(Exception):
    """Base exception for all data analyzer errors."""

    pass


class ColumnNotFoundError(DataAnalyzerError):
    """Raised when a specified column is not found in the dataset."""

    pass


class JoinError(DataAnalyzerError):
    """Raised when a join operation fails."""

    pass


class DataCleaningError(DataAnalyzerError):
    """Raised when a data cleaning operation fails."""

    pass


class FileLoadError(DataAnalyzerError):
    """Raised when loading a file fails."""

    pass


class DatasetNotFoundError(ValueError):
    """Raised when a dataset is not found in the internal store."""

    pass


class InvalidQueryError(ValueError):
    """Raised when a query string fails to execute."""

    pass


class UnsupportedFormatError(ValueError):
    """Raised when an unsupported file format is provided for loading."""

    pass


class InvalidTransformationError(ValueError):
    """Raised when a transformation step is invalid or improperly formatted."""

    pass
