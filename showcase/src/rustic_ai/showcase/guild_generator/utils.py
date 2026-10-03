"""
Utility functions for the Guild Generator module.
"""

import re


def extract_json_from_response(response_text: str) -> str:
    """
    Extract JSON from response text that may be wrapped in markdown code blocks.

    This utility handles LLM responses that may include JSON in markdown code blocks
    or mixed with explanatory text.

    Args:
        response_text: The raw response text from an LLM

    Returns:
        Extracted JSON string, or original text if no JSON patterns found

    Examples:
        >>> extract_json_from_response('```json\\n{"key": "value"}\\n```')
        '{"key": "value"}'

        >>> extract_json_from_response('Here is the result: {"key": "value"}')
        '{"key": "value"}'
    """
    text = response_text.strip()

    # Try to find JSON in markdown code blocks
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(code_block_pattern, text)
    if matches:
        # Return the first code block content
        return matches[0].strip()

    # If no code blocks, try to find JSON object directly
    # Look for content starting with { and ending with }
    json_pattern = r"(\{[\s\S]*\})"
    matches = re.findall(json_pattern, text)
    if matches:
        return matches[0].strip()

    # Return original text if no patterns match
    return text
