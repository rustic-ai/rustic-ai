"""Plain LLM imports must not eagerly require retired KB modules or Uniko."""

import subprocess
import sys


def test_plain_llm_import_without_optional_memory_backends():
    program = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('rustic_ai.core.knowledgebase', 'rustic_ai.uniko_agent', 'uniko', 'rustic_ai.lancedb')):
            raise ImportError('optional backend blocked')
sys.meta_path.insert(0, BlockOptional())
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.memories import QueueBasedMemoriesStore
assert LLMAgent and QueueBasedMemoriesStore
"""
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
