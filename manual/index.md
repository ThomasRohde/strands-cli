---
title: Home
description: Execute declarative agentic workflows with strong observability and schema validation
keywords: strands, cli, workflow, agent, llm, bedrock, ollama, openai, yaml, json schema, observability, telemetry
---

# Strands CLI Documentation

<div align="center">
<img src="images/strands_logo.svg" alt="Strands CLI Logo" width="120" height="120" />
</div>

Welcome to the **Strands CLI** documentation. Strands CLI is a powerful command-line tool for executing agentic workflows with strong observability, schema validation, and safe orchestration.

## What is Strands CLI?

Strands CLI allows you to define and execute complex agentic workflows using YAML/JSON specifications. It supports multiple AI providers (Ollama, AWS Bedrock, OpenAI) and provides sophisticated patterns for orchestrating multi-agent systems.

## Key Features

- **Multiple Execution Patterns**: Chain, Workflow (DAG), Routing, Parallel, Evaluator-Optimizer, Graph, and Orchestrator-Workers
- **Durable Session Management**: Automatic crash recovery, workflow resume, and agent conversation restoration
- **Human-in-the-Loop (HITL)**: Pause workflows for human approval, quality control, and interactive decision-making
- **Multi-Provider Support**: Works with Ollama, AWS Bedrock, and OpenAI
- **Strong Observability**: Built-in OpenTelemetry instrumentation with trace exports
- **Schema Validation**: JSON Schema Draft 2020-12 validation for workflow specifications
- **Context Management**: Intelligent context handling with presets and compaction strategies
- **Security First**: Sandboxed templating, SSRF prevention, and path traversal protection
- **Token Budgets**: Fine-grained control over token usage and costs
- **MCP Integration**: Support for Model Context Protocol servers and tools

## Getting Started

Choose a quickstart tutorial based on your preferred AI provider:

- [Quickstart with Ollama](tutorials/quickstart-ollama.md) - Local, open-source models
- [Quickstart with AWS Bedrock](tutorials/quickstart-bedrock.md) - Enterprise cloud AI
- [Quickstart with OpenAI](tutorials/quickstart-openai.md) - GPT models

## Documentation Structure

This documentation follows the [Diátaxis](https://diataxis.fr/) framework:

- **[Tutorials](tutorials/quickstart-ollama.md)**: Step-by-step learning paths for new users
- **[How-To Guides](howto/run-workflows.md)**: Task-oriented guides for common operations
- **[Explanation](explanation/architecture.md)**: Conceptual understanding and architecture
- **[Reference](reference/cli.md)**: Technical reference documentation

## Installation

```bash
# Using pip
pip install strands-cli

# Using uv (recommended)
uv pip install strands-cli

# With documentation dependencies
uv pip install -e ".[docs]"
```

## Quick Example

```yaml
# simple-workflow.yaml
version: "1.0"
name: "Hello Strands"
description: "A simple single-agent workflow"

provider:
  type: ollama
  model: llama3.2

agents:
  - name: greeter
    role: Friendly AI Assistant
    goal: Greet the user warmly

pattern:
  type: single_agent
  agent: greeter
  input: "Hello! Tell me about Strands CLI."
```

Run it:

```bash
strands run simple-workflow.yaml
```

## Next Steps

- Learn about [workflow patterns](explanation/patterns.md)
- Explore [example workflows](reference/examples.md)
- Understand the [architecture](explanation/architecture.md)
- Read the [CLI reference](reference/cli.md)

## Support

- **GitHub**: [ThomasRohde/strands-cli](https://github.com/ThomasRohde/strands-cli)
- **Issues**: [Report bugs or request features](https://github.com/ThomasRohde/strands-cli/issues)
- **License**: Apache-2.0
