"""Constants for the knowledge base module."""

# File sizes
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
DEFAULT_TEXT_CHUNK_SIZE = 4000  # characters
DEFAULT_TEXT_OVERLAP = 200  # characters

# Encodings
DEFAULT_ENCODING = "utf-8"
ENCODING_ERRORS = "ignore"  # How to handle encoding errors

# File and directory names
KNOL_META_FILENAME = ".knol"
KNOL_OLD_META_FILENAME = ".meta"  # Legacy
CONTENT_FILENAME = "content"
LIBRARY_DIR = "library"
CHUNKS_DIR_PREFIX = "chunks_"
BYTES_SUBDIR = "bytes"
PREVIEWS_SUBDIR = "previews"

# File extensions
DEFAULT_BINARY_EXT = "bin"
DEFAULT_TEXT_EXT = "txt"
DEFAULT_JSON_EXT = "json"

# Chunk ID formatting
CHUNK_ID_PATTERN = "{knol_id}:{chunker_name}:{index}"
CHUNK_FILENAME_PATTERN = "{index:06d}.{ext}"  # Zero-padded to 6 digits

# Timeout and retry settings
DEFAULT_READ_TIMEOUT = 30  # seconds
DEFAULT_WRITE_TIMEOUT = 60  # seconds

# Media type patterns
TEXT_LIKE_TYPES = {"text", "application"}  # Major MIME types treated as text
IMAGE_TYPES = {"image"}
AUDIO_TYPES = {"audio"}
VIDEO_TYPES = {"video"}
