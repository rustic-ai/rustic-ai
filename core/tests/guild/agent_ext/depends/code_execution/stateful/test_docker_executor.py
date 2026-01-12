import pytest

from rustic_ai.core.guild.agent_ext.depends.code_execution.stateful import (
    CodeSnippet,
    DockerExecutor,
)

# Check if docker is available and reachable
docker_available = False
try:
    import docker
    client = docker.from_env()
    client.ping()
    docker_available = True
except Exception as exc:
    # Any failure here means Docker is not usable; tests will be skipped.
    docker_available = False


@pytest.mark.skipif(not docker_available, reason="Docker daemon not available")
class TestDockerExecutor:

    @pytest.fixture
    def executor(self):
        executor = DockerExecutor(image="python:3.12-slim", timeout=30)
        yield executor
        executor.shutdown()

    def test_basic_execution(self, executor):
        """Test basic code execution in Docker"""
        snippet = CodeSnippet(language="python", code='print("Hello from Docker")')
        result = executor.run(snippet)

        assert result.exit_code == 0
        assert "Hello from Docker" in result.stdout.strip()
        assert result.stderr == ""

    def test_python_version(self, executor):
        """Test that we are running in the expected container environment"""
        snippet = CodeSnippet(language="python", code="import sys; print(f'Version: {sys.version}')")
        result = executor.run(snippet)

        assert result.exit_code == 0
        assert "3.12" in result.stdout

    def test_stateless_execution(self, executor):
        """Test that execution is stateless (new container per run)"""
        # First execution sets a file
        snippet1 = CodeSnippet(
            language="python",
            code="with open('test.txt', 'w') as f: f.write('persistent?')"
        )
        result1 = executor.run(snippet1)
        assert result1.exit_code == 0

        # Second execution checks for file
        snippet2 = CodeSnippet(
            language="python",
            code="import os; print(os.path.exists('test.txt'))"
        )
        result2 = executor.run(snippet2)
        assert result2.exit_code == 0
        # Should be False because containers are ephemeral
        assert "False" in result2.stdout

    def test_input_output_files(self, executor):
        """Test file injection and retrieval"""
        code = """
with open('input.txt', 'r') as f:
    content = f.read()

with open('output.txt', 'w') as f:
    f.write(content.upper())
"""
        snippet = CodeSnippet(language="python", code=code)

        result = executor.run(
            snippet,
            input_files={"input.txt": b"hello world"},
            output_filenames=["output.txt"]
        )

        assert result.exit_code == 0
        assert "output.txt" in result.output_files
        assert result.output_files["output.txt"] == b"HELLO WORLD"

    def test_runtime_error(self, executor):
        """Test handling of runtime errors in container"""
        snippet = CodeSnippet(language="python", code="raise ValueError('Boom')")
        result = executor.run(snippet)

        assert result.exit_code != 0
        # Checks depend on how Docker logs capture traceback
        assert "ValueError: Boom" in result.stderr

    def test_timeout(self, executor):
        """Test execution timeout"""
        # We need a smaller timeout for the test
        executor.timeout = 2
        snippet = CodeSnippet(language="python", code="import time; time.sleep(5)")

        # Docker client might raise exception or just return timeout
        # The implementation relies on container.wait(timeout=...)
        # which raises ReadTimeout or similar from requests/urllib3 usually if using older docker-py,
        # or the wrapper should handle it.
        # Let's see what happens.

        # In implementation: result = container.wait(timeout=timeout_seconds)
        # Verify if it handles the timeout exception cleanly or propagates it.
        # The implementation catches Exception and returns ExecutionResult with exception.

        result = executor.run(snippet)
        assert result.exit_code == -1
        assert result.exception is not None
        # The exact exception message might vary, but capturing it ensures we don't crash
