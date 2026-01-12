import io
import tarfile
from typing import Dict, List, Optional, Set

try:
    import docker
    from docker.models.containers import Container
except ImportError:
    docker = None

from .code_executor import CodeExecutor
from .exceptions import ExecutorError
from .models import CodeSnippet, ExecutionException, ExecutionResult


class DockerExecutor(CodeExecutor):
    """
    Executes code snippets in a Docker container for isolation.

    Requires the 'docker' python package and a running Docker daemon.
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout: int = 10,
        network_disabled: bool = True,
        cpu_quota: int = 100000,
        mem_limit: str = "512m",
    ):
        super().__init__()
        if docker is None:
            raise ImportError("The 'docker' package is required for DockerExecutor.")

        try:
            self.client = docker.from_env()
        except Exception as e:
            raise ExecutorError(f"Failed to connect to Docker daemon: {e}")

        self.image = image
        self.timeout = timeout
        self.network_disabled = network_disabled
        self.cpu_quota = cpu_quota  # 100000 = 100% of 1 CPU
        self.mem_limit = mem_limit

    @property
    def supported_languages(self) -> Set[str]:
        return {"python"}

    def _do_run(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int],
        input_files: Optional[Dict[str, bytes]],
        output_filenames: Optional[List[str]],
    ) -> ExecutionResult:
        if timeout_seconds is None:
            timeout_seconds = self.timeout

        container: Optional[Container] = None
        try:
            # Prepare script content
            # We run a loop to keep the container alive if we want stateful?
            # For now, this implementation is STATLESS per run, unless we modify it to keep container running.
            # The prompt asked for "Sandbox" which usually implies we can run multiple commands.
            # However, looking at the base `_do_run`, it takes a snippet.
            # Ideally for stateual sessions we'd keep the container.
            # Let's keep it simple: Ephemeral container for now, as that's safer.
            # If we want stateful, we'd need to start container in __init__ and reuse it.

            # We will use a simple ephemeral container for this implementation steps first.
            cmd = ["python", "/sandbox/script.py"]

            container = self.client.containers.create(
                self.image,
                command=cmd,
                working_dir="/sandbox",
                detach=True,
                network_disabled=self.network_disabled,
                mem_limit=self.mem_limit,
                cpu_quota=self.cpu_quota,
                tty=False,
            )

            # Copy script
            self._copy_to_container(container, "/sandbox/script.py", code.code)

            # Copy input files
            if input_files:
                for name, content in input_files.items():
                    self._copy_to_container(container, f"/sandbox/{name}", content)

            # Start
            container.start()

            # Wait
            result = container.wait(timeout=timeout_seconds)
            exit_code = result.get("StatusCode", 0)

            # Logs
            # Docker returns bytes, we decode. Use simple decode for now.
            # Ideally split streams.
            # docker-py logs() returns both combined if `stream=False`.
            # To get separate, we can call twice or use demux=True (if supported).
            # demux=True returns (stdout, stderr) tuple since 3.0.0
            stdout_bytes, stderr_bytes = container.logs(stdout=True, stderr=True, stream=False, demux=True)

            stdout = stdout_bytes.decode("utf-8") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8") if stderr_bytes else ""

            # Retrieve output files
            output_files_dict = {}
            if output_filenames:
                for name in output_filenames:
                    try:
                        content = self._copy_from_container(container, f"/sandbox/{name}")
                        output_files_dict[name] = content
                    except Exception:
                        pass  # File maybe not created

            return ExecutionResult(
                input_snippet=code,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                output_files=output_files_dict,
            )

        except Exception as e:
            return ExecutionResult(
                input_snippet=code,
                exit_code=-1,
                exception=ExecutionException.from_exception(e),
            )
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _copy_to_container(self, container, path, content: str | bytes):
        if isinstance(content, str):
            content = content.encode("utf-8")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name=path.split("/")[-1])
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        # Put archive expects the PARENT directory
        parent_dir = path.rsplit("/", 1)[0]
        container.put_archive(parent_dir, tar_stream)

    def _copy_from_container(self, container, path) -> bytes:
        bits, _ = container.get_archive(path)
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            member = tar.next()
            if member is None:
                raise RuntimeError(f"No file found in archive for {path}")
            file_obj = tar.extractfile(member)
            if file_obj is None:
                raise RuntimeError(f"Could not extract file {path}")
            return file_obj.read()

    def _do_shutdown(self) -> None:
        if hasattr(self, "client"):
            self.client.close()
