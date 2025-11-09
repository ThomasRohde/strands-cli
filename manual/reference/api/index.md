# API Reference

Complete Python API documentation for Strands CLI.

## Module Overview

Strands CLI is organized into several key modules:

### Core Modules

- **[Runtime](runtime.md)** - Provider adapters, context management, and budget enforcement
- **[Execution](exec.md)** - Workflow pattern executors (chain, workflow, routing, etc.)
- **[Loader](loader.md)** - YAML/JSON parsing and template rendering
- **[Schema](schema.md)** - JSON Schema validation and Pydantic models
- **[Telemetry](telemetry.md)** - OpenTelemetry tracing and PII redaction

### Supporting Modules

- **[Tools](tools.md)** - Native tool registry and implementations
- **[Artifacts](artifacts.md)** - Artifact I/O operations
- **[Visualization](visualization.md)** - Graph pattern visualization
- **[Capability](capability.md)** - Feature compatibility checking

## Quick Links

- [Types and Models](types.md) - Core Pydantic models
- [Configuration](config.md) - Environment variable configuration
- [Exit Codes](exit-codes.md) - Standard exit codes
- [Utilities](utils.md) - Shared utilities

## Usage

All public APIs are importable from their respective modules:

```python
from strands_cli.types import Spec, Runtime, Agent
from strands_cli.loader import load_workflow_spec
from strands_cli.runtime.providers import create_model
from strands_cli.exec.chain import run_chain
```

## Type Hints

All modules use strict type hints and are checked with Mypy. See individual module documentation for detailed type signatures.
