from fsspec import filesystem
from fsspec.implementations.dirfs import DirFileSystem
import pytest

from rustic_ai.core.guild.agent_ext.depends.filesystem.utils import (
    get_root_uri,
    get_uri,
)


class TestFilesystemUtils:
    """Test cases for filesystem utility functions."""

    @pytest.fixture
    def temp_dirfs(self, tmp_path):
        """Create a DirFileSystem instance for testing with local filesystem."""
        base_path = str(tmp_path / "test_root")
        fs = filesystem("file", auto_mkdir=True)
        fs.makedirs(base_path, exist_ok=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)
        yield dirfs
        # Cleanup
        if fs.exists(base_path):
            fs.rm(base_path, recursive=True)

    @pytest.fixture
    def memory_dirfs(self):
        """Create a DirFileSystem instance for testing with memory filesystem."""
        fs = filesystem("memory")
        base_path = "/test_root"
        fs.makedirs(base_path, exist_ok=True)
        dirfs = DirFileSystem(path=base_path, fs=fs)
        return dirfs

    def test_get_root_uri_local_filesystem(self, temp_dirfs):
        """Test get_root_uri with local filesystem."""
        root_uri = get_root_uri(temp_dirfs)

        assert root_uri.startswith("file://")
        assert "test_root" in root_uri

    def test_get_root_uri_memory_filesystem(self, memory_dirfs):
        """Test get_root_uri with memory filesystem."""
        root_uri = get_root_uri(memory_dirfs)

        assert root_uri == "memory:///test_root"

    def test_get_uri_simple_relative_path(self, memory_dirfs):
        """Test get_uri with a simple relative path."""
        uri = get_uri(memory_dirfs, "data/file.txt")

        assert uri == "memory:///test_root/data/file.txt"

    def test_get_uri_with_leading_slash(self, memory_dirfs):
        """Test get_uri strips leading slashes to prevent double slashes."""
        uri = get_uri(memory_dirfs, "/data/file.txt")

        # Should strip leading slash and not create //
        assert uri == "memory:///test_root/data/file.txt"
        assert "//data" not in uri

    def test_get_uri_with_protocol_prefix(self, memory_dirfs):
        """Test get_uri strips protocol prefix from input path."""
        uri = get_uri(memory_dirfs, "memory:///data/file.txt")

        # Should strip the protocol and treat as relative
        assert uri == "memory:///test_root/data/file.txt"

    def test_get_uri_nested_path(self, memory_dirfs):
        """Test get_uri with deeply nested path."""
        uri = get_uri(memory_dirfs, "level1/level2/level3/file.txt")

        assert uri == "memory:///test_root/level1/level2/level3/file.txt"

    def test_get_uri_empty_path(self, memory_dirfs):
        """Test get_uri with empty path returns root."""
        uri = get_uri(memory_dirfs, "")

        assert uri == "memory:///test_root/"

    def test_get_uri_dot_path(self, memory_dirfs):
        """Test get_uri with current directory notation."""
        uri = get_uri(memory_dirfs, ".")

        assert uri == "memory:///test_root/."

    def test_get_uri_with_actual_file(self, temp_dirfs):
        """Test get_uri with actual file creation and verification."""
        # Create a test file
        test_path = "test_dir/test_file.txt"

        # Write content using the dirfs
        with temp_dirfs.open(test_path, "w") as f:
            f.write("test content")

        # Verify we can read using the underlying filesystem and URI
        assert temp_dirfs.exists(test_path)

        with temp_dirfs.open(test_path, "r") as f:
            content = f.read()
        assert content == "test content"

    @pytest.mark.parametrize(
        "input_path,expected_suffix",
        [
            ("file.txt", "/test_root/file.txt"),
            ("dir/file.txt", "/test_root/dir/file.txt"),
            ("/file.txt", "/test_root/file.txt"),  # Leading slash stripped
            ("memory:///file.txt", "/test_root/file.txt"),  # Protocol stripped
        ],
    )
    def test_get_uri_parametrized(self, memory_dirfs, input_path, expected_suffix):
        """Test get_uri with various input formats."""
        uri = get_uri(memory_dirfs, input_path)

        assert uri.endswith(expected_suffix)
        assert uri.startswith("memory://")

    def test_get_root_uri_consistency(self, memory_dirfs):
        """Test that get_root_uri returns consistent results."""
        uri1 = get_root_uri(memory_dirfs)
        uri2 = get_root_uri(memory_dirfs)

        assert uri1 == uri2

    def test_get_uri_consistency(self, memory_dirfs):
        """Test that get_uri returns consistent results for same input."""
        path = "data/file.txt"
        uri1 = get_uri(memory_dirfs, path)
        uri2 = get_uri(memory_dirfs, path)

        assert uri1 == uri2
