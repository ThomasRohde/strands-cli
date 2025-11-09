# Schema Reference

Complete JSON Schema reference for Strands workflow specifications.

## Overview

**Schema Title**: Strands Workflow Spec (v0)

**Description**: Declarative spec for executing agentic workflows (CLI) on AWS Strands SDK. Captures runtime, agents, tools, and Anthropic-style patterns (chain, routing, orchestrator-workers, evaluator-optimizer, graph, workflow).

**Schema Version**: https://json-schema.org/draft/2020-12/schema

## Top-Level Properties

### `version` **Required**

**Type**: `integer | string`

Spec version. Use 0 initially.

---

### `name` **Required**

**Type**: `string`

No description available.

---

### `description` *Optional*

**Type**: `string`

No description available.

---

### `tags` *Optional*

**Type**: `array`

No description available.

---

### `runtime` **Required**

**Type**: `object`

No description available.

---

### `inputs` *Optional*

**Type**: `object`

No description available.

---

### `env` *Optional*

**Type**: `object`

No description available.

---

### `telemetry` *Optional*

**Type**: `object`

No description available.

---

### `context_policy` *Optional*

**Type**: `object`

No description available.

---

### `skills` *Optional*

**Type**: `array`

No description available.

---

### `tools` *Optional*

**Type**: `object`

No description available.

---

### `agents` **Required**

**Type**: `object`

Map of agent name -> spec

---

### `pattern` **Required**

**Type**: `object`

No description available.

---

### `outputs` *Optional*

**Type**: `object`

No description available.

---

### `security` *Optional*

**Type**: `object`

No description available.

---


## Schema Definitions

The schema includes the following reusable definitions in `$defs`:

- `agentSpec`
- `agents`
- `chainConfig`
- `contextPolicy`
- `env`
- `evaluatorOptimizerConfig`
- `graphConfig`
- `identifier`
- `inference`
- `inputVarMap`
- `inputVarSpec`
- `inputs`
- `nonEmptyString`
- `orchestratorWorkersConfig`
- `outputs`
- `parallelConfig`
- `pattern`
- `routingConfig`
- `runtime`
- `security`
- `skills`
- `step`
- `tag`
- `telemetry`
- `tools`
- `workflowConfig`

## See Also

- [CLI Reference](cli.md) - Command-line interface
- [Examples](examples.md) - Example workflows
- [Tutorials](../tutorials/quickstart-ollama.md) - Getting started