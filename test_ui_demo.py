#!/usr/bin/env python
"""Quick demo of the improved --ask UI."""

from strands_cli.loader.variable_prompter import prompt_for_missing_variables
from strands_cli.types import Spec

# Create a demo spec with the same variables as the research agent
spec = Spec(
    name="demo",
    version=1,
    runtime={"provider": "openai", "model_id": "gpt-4o-mini"},
    agents={"agent1": {"prompt": "test"}},
    pattern={"type": "chain", "config": {"steps": []}},
    inputs={
        "required": {
            "topic": {
                "type": "string",
                "description": "Research topic or question to investigate deeply"
            },
            "depth": {
                "type": "string",
                "description": "Research depth level",
                "enum": ["quick", "standard", "comprehensive"]
            },
            "max_sources": {
                "type": "integer",
                "description": "Maximum sources per search (3-10 recommended)"
            }
        },
        "values": {}
    }
)

# Simulate the interactive prompting
print("\n" + "="*70)
print("IMPROVED --ask FLAG UI DEMO")
print("="*70)

missing_vars = ["topic", "depth", "max_sources"]
result = prompt_for_missing_variables(spec, missing_vars)

print("\n" + "="*70)
print("COLLECTED VALUES:")
print("="*70)
for key, value in result.items():
    print(f"  {key}: {value!r} (type: {type(value).__name__})")
print()
