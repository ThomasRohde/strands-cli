# Schema Reference

Complete JSON Schema reference for Strands workflow specifications.

> **Note**: This documentation is auto-generated from `strands-workflow.schema.json`.
> For a more narrative guide, see the [Workflow Manual](workflow-manual.md).

## Overview

**Schema Title**: Strands Workflow Spec (v0)

**Description**: Declarative spec for executing agentic workflows (CLI) on AWS Strands SDK. Captures runtime, agents, tools, and Anthropic-style patterns (chain, routing, orchestrator-workers, evaluator-optimizer, graph, workflow).

**Schema Version**: https://json-schema.org/draft/2020-12/schema

## Quick Links

- [Top-Level Properties](#top-level-properties)
- [Schema Definitions](#schema-definitions)
- [Workflow Patterns](#workflow-patterns)
- [See Also](#see-also)

## Top-Level Properties

These are the root properties of a workflow specification file:

### `version` **Required**

**Type**: `integer` | `string`

Spec version. Use 0 initially.

---

### `name` **Required**

**Type**: `string` (see [`nonEmptyString`](#nonemptystring))

Unique identifier for this workflow. Used in telemetry, logging, and artifact paths. Should be descriptive and URL-safe (no spaces).

**Constraints**:

- Min length: `1`

**Examples**:

```
research-brief
```
```
code-review-pipeline
```
```
data-processing
```

---

### `description` *Optional*

**Type**: `string`

Human-readable description of workflow purpose, behavior, and use cases. Displayed in logs and used for documentation generation.

**Examples**:

```
Multi-step research workflow that gathers sources, analyzes content, and produces a comprehensive brief
```

---

### `tags` *Optional*

**Type**: `array`

Classification tags for organizing and filtering workflows. Useful for tooling, CI/CD pipelines, and workflow discovery. Tags must be lowercase alphanumeric with dots, hyphens, or underscores.

**Constraints**:

- Items must be unique

**Examples**:

```yaml
[
  "research",
  "production",
  "experimental"
]
```
```yaml
[
  "data-processing",
  "ml-training"
]
```

---

### `runtime` **Required**

**Type**: `object` (see [`runtime`](#runtime))

Default runtime configuration for all agents including LLM provider, model selection, inference parameters, budgets, and failure handling. Individual agents can override specific settings.


#### Properties

**`provider`** (**required**)

- Type: `string`
- LLM provider identifier (e.g., bedrock, openai, azure_openai, danskegpt, local).

**`model_id`** (*optional*)

- Type: `string`
- Default model for agents that don't override.

**`region`** (*optional*)

- Type: `string`
- AWS region for Bedrock provider (e.g., 'us-east-1', 'eu-central-1'). Required when provider is 'bedrock'. Ignored for other providers.

**`host`** (*optional*)

- Type: `string`
- Server host URL for providers like Ollama or OpenAI-compatible servers (e.g., http://localhost:11434).
- Format: `uri`

**`space_id`** (*optional*)

- Type: `string`
- Space identifier for DanskeGPT provider (required when provider is danskegpt).

**`temperature`** (*optional*)

- Type: `number`
- Sampling temperature for generation.
- Minimum: `0.0`
- Maximum: `2.0`

**`top_p`** (*optional*)

- Type: `number`
- Nucleus sampling parameter.
- Minimum: `0.0`
- Maximum: `1.0`

**`max_tokens`** (*optional*)

- Type: `integer`
- Maximum tokens to generate.
- Minimum: `1`

**`max_parallel`** (*optional*)

- Type: `integer`
- Maximum number of concurrent agent invocations in parallel patterns (parallel branches, workflow tasks, orchestrator workers). Controls resource usage and API rate limit management. Default varies by pattern.
- Minimum: `1`
- Default: `5`

**`budgets`** (*optional*)

- Type: `object`
- Resource limits and cost controls for workflow execution. Enforced at runtime with graceful failures and warnings.

**`failure_policy`** (*optional*)

- Type: `object`
- Retry and backoff configuration for transient failures (network errors, rate limits, timeouts). Applied to all agent invocations unless overridden.

---

### `inputs` *Optional*

**Type**: `object` (see [`inputs`](#inputs))

Declare workflow parameters that can be provided via --var flags or defaults. Supports type validation and optional/required semantics. Use Jinja2 templates ({{variable_name}}) in prompts and inputs to reference these values.


#### Properties

**`required`** (*optional*)

- Type: `object`
- Required input parameters that must be provided via --var flags or have defaults. Workflow fails if required parameters without defaults are missing.

**`optional`** (*optional*)

- Type: `object`
- Optional input parameters that can be omitted. Use with default values or conditional templates (e.g., {{param|default:'fallback'}}).

**`values`** (*optional*)

- Type: `object`
- Actual input values provided at runtime (e.g., via --var flags or defaults). Typically populated by CLI during execution, not manually specified in workflow file.

---

### `env` *Optional*

**Type**: `object` (see [`env`](#env))

Environment configuration including secrets (API keys, tokens) and filesystem mounts. Secrets can be sourced from environment variables, AWS Secrets Manager, SSM Parameter Store, or files. Mounts map logical names to local paths for file access.


#### Properties

**`secrets`** (*optional*)

- Type: `array`
- Secret definitions for sensitive data like API keys, tokens, and credentials. Values are never logged or included in telemetry.

**`mounts`** (*optional*)

- Type: `object`
- Logical mount name to local path mappings. Allows tools to access files in specified directories (e.g., 'workspace': '/home/user/project'). Used for file read/write operations.

---

### `telemetry` *Optional*

**Type**: `object` (see [`telemetry`](#telemetry))

OpenTelemetry (OTEL) configuration for distributed tracing and observability. Configure OTLP endpoint, service name, sampling ratio, and redaction policies for sensitive data in tool inputs/outputs.


#### Properties

**`otel`** (*optional*)

- Type: `object`
- OTEL exporter configuration. Spans include workflow execution, agent invocations, tool calls, and LLM completions.

**`redact`** (*optional*)

- Type: `object`
- Redaction policies for sensitive data in traces. Prevents PII and credentials from appearing in telemetry backends.

---

### `context_policy` *Optional*

**Type**: `object` (see [`contextPolicy`](#contextpolicy))

Advanced context management strategies including automatic conversation compaction (summarization), persistent notes storage, and just-in-time retrieval tools. Helps manage token budgets and maintain long-running agent conversations.


#### Properties

**`compaction`** (*optional*)

- Type: `object`
- Automatic context window compression via summarization of older messages. Prevents token limit overflow in long-running workflows by condensing conversation history while preserving recent exchanges.

**`notes`** (*optional*)

- Type: `object`
- Persistent notes file for capturing key insights across workflow steps. Agents can write to notes file, and recent notes are automatically included in subsequent agent contexts for cross-step memory.

**`retrieval`** (*optional*)

- Type: `object`
- Configuration for Just-In-Time (JIT) retrieval tools that provide file system access during agent execution.

---

### `skills` *Optional*

**Type**: `array` (see [`skills`](#skills))

Skill bundles containing code, documentation, or assets that agents can reference. Skills are injected into agent system prompts as metadata (id/path). Executable skill support is planned for future versions.

---

### `tools` *Optional*

**Type**: `object` (see [`tools`](#tools))

Tool definitions available to agents. Supports three types: (1) Python callables from allowlisted modules, (2) Model Context Protocol (MCP) servers via stdio or HTTPS, and (3) HTTP executors for REST APIs. Tools can be assigned globally or per-agent.


#### Properties

**`python`** (*optional*)

- Type: `array`
- Python callable tools imported from modules. MVP supports allowlisted callables (strands_tools.http_request, strands_tools.file_read) and native tools with TOOL_SPEC pattern. Tools must return ToolResult dict with toolUseId, status, and content fields.

**`mcp`** (*optional*)

- Type: `array`

**`http_executors`** (*optional*)

- Type: `array`

---

### `agents` **Required**

**Type**: `object` (see [`agents`](#agents))

Map of agent identifiers to specifications. Each agent has a unique system prompt, optional tools, and can override runtime model/provider settings. Agents are referenced by ID in workflow patterns. Minimum 1 agent required.

---

### `pattern` **Required**

**Type**: `object` (see [`pattern`](#pattern))

Workflow execution pattern defining agent orchestration. Supported patterns: chain (sequential steps), workflow (DAG with dependencies), routing (dynamic agent selection), parallel (concurrent branches), evaluator-optimizer (iterative refinement), orchestrator-workers (task decomposition), and graph (state machine with conditional transitions).


#### Properties

**`type`** (**required**)

- Type: `string`
- Allowed values: `chain`, `routing`, `parallel`, `orchestrator_workers`, `evaluator_optimizer`, `graph`, `workflow`

**`config`** (**required**)

- Type: `chainConfig` | `routingConfig` | `parallelConfig` | `orchestratorWorkersConfig` | `evaluatorOptimizerConfig` | `graphConfig` | `workflowConfig`

---

### `outputs` *Optional*

**Type**: `object` (see [`outputs`](#outputs))

Define artifacts (files) to write after workflow execution. Supports Jinja2 templates to reference agent responses from steps, tasks, branches, or nodes. Use {{ last_response }} for final output or pattern-specific variables like {{ steps[0].response }}.


#### Properties

**`artifacts`** (*optional*)

- Type: `array`

---

### `security` *Optional*

**Type**: `object` (see [`security`](#security))

Security guardrails including network access controls, PII redaction, and tool allowlisting. Guardrail settings are parsed but enforcement is logged only in current version (full enforcement planned for future release).


#### Properties

**`guardrails`** (*optional*)

- Type: `object`
- Security guardrails to restrict agent capabilities and prevent unsafe operations. Parsed in MVP for validation but not enforced during execution.

---


## Schema Definitions

The following types are referenced throughout the schema using `$ref`.
Click each definition to see detailed property documentation.

### Workflow Patterns

These definitions configure the seven supported workflow patterns. See [Pattern Explanations](../explanation/patterns.md) for usage guidance.

#### `chainConfig`

Sequential chain pattern configuration. Executes steps in order, passing context between steps. Each step can access previous step responses via {{steps[n].response}} templates. Supports human-in-the-loop (HITL) pause points.

**Type**: `object`

##### Properties

**`steps`** (**required**)

- Type: `array`
- Ordered list of agent execution or HITL steps. Steps execute sequentially with full conversation context. Minimum 1 step required.

---

#### `workflowConfig`

Directed Acyclic Graph (DAG) workflow pattern. Tasks execute in parallel when dependencies are met. Use 'deps' array to specify task dependencies. Tasks reference other task outputs via {{tasks.<id>.response}} templates.

**Type**: `object`

##### Properties

**`tasks`** (**required**)

- Type: `array`
- List of tasks with dependency relationships. Tasks without dependencies start immediately. Tasks with dependencies wait for all deps to complete before starting. Enables parallel execution paths.

---

#### `routingConfig`

Dynamic routing pattern. Router agent analyzes input and selects execution path from predefined routes. Router returns JSON with 'route' key. Each route can have sequential steps. Supports optional HITL review of router decision.

**Type**: `object`

##### Properties

**`router`** (**required**)

- Type: `object`
- Router agent configuration responsible for analyzing input and deciding execution path.

**`routes`** (**required**)

- Type: `object`
- Map of route IDs to execution paths. Router's 'route' value must match one of these keys. Each route defines sequential steps to execute for that path.

---

#### `parallelConfig`

Parallel branches pattern. Executes multiple independent execution branches concurrently, then optionally aggregates results with a reduce step. Each branch can have multiple sequential steps. Branch results accessible via {{branches.<id>.response}} templates.

**Type**: `object`

##### Properties

**`branches`** (**required**)

- Type: `array`
- List of independent execution branches. Each branch executes its steps sequentially. All branches run concurrently (up to runtime.max_parallel limit). Minimum 2 branches required.

**`reduce`** (*optional*)

- Type: `object`
- Optional reduce step that aggregates results from all branches. Has access to all branch outputs via {{branches.<id>.response}} templates. Commonly used for synthesis, comparison, or consensus building.

---

#### `evaluatorOptimizerConfig`

Iterative refinement pattern. Producer agent generates draft, evaluator scores it (0-100), and producer revises based on feedback until score meets acceptance criteria or max iterations reached. Useful for quality control, writing refinement, and code review.

**Type**: `object`

##### Properties

**`producer`** (**required**)

- Type: `string`
- Agent that produces the draft/artifact. Receives evaluator feedback in subsequent iterations and revises accordingly. First iteration starts fresh, later iterations receive previous draft and evaluation feedback.

**`evaluator`** (**required**)

- Type: `object`
- Evaluator agent configuration. Must return JSON with 'score' (0-100 integer), 'reasoning', and 'suggestions' fields.

**`accept`** (**required**)

- Type: `object`
- Acceptance criteria for terminating iteration loop. Iteration stops when score >= min_score OR max_iters reached.

**`revise_prompt`** (*optional*)

- Type: `string`
- Optional custom prompt for revision iterations. If omitted, default revision prompt includes previous draft and evaluator feedback. Supports templates to customize revision instructions.

**`review_gate`** (*optional*)

- Type: `object`
- Optional human review gate between evaluation iterations. Pauses execution after evaluation to allow user review before continuing to next iteration.

---

#### `orchestratorWorkersConfig`

Orchestrator-workers pattern for divide-and-conquer task decomposition. Orchestrator agent breaks down complex tasks into subtasks, worker agents execute them in parallel (respecting runtime.max_parallel), and optional reduce/writeup steps aggregate results. Useful for research, data processing, and parallelizable workflows.

**Type**: `object`

##### Properties

**`orchestrator`** (**required**)

- Type: `object`
- Orchestrator agent configuration. This agent analyzes the main task and generates a structured JSON list of subtasks for workers to execute. Must return JSON array with task objects (each containing 'description' and optional 'context').

**`decomposition_review`** (*optional*)

- Type: `object`
- Optional human review gate after task decomposition. Pauses execution to allow user review of subtasks before delegating to workers.

**`worker_template`** (**required**)

- Type: `object`
- Worker agent template applied to each decomposed subtask. Workers execute in parallel (respecting runtime.max_parallel) and receive subtask description + optional context from orchestrator. All workers use the same agent configuration.

**`reduce_review`** (*optional*)

- Type: `object`
- Optional human review gate before reduce step. Pauses execution to allow user review of worker results before aggregation.

**`reduce`** (*optional*)

- Type: `object`
- Optional aggregation step to combine worker results. Agent receives array of worker outputs and synthesizes a unified response. Use templates like {{ workers }} to reference worker results. If omitted, writeup step receives raw worker array.

**`writeup`** (*optional*)

- Type: `object`
- Optional final synthesis step to produce comprehensive report. Agent receives orchestrator output, worker results, and optional reduce output to generate final deliverable. Supports templates like {{ orchestrator_response }}, {{ workers }}, {{ reduce_response }}.

---

#### `graphConfig`

Graph pattern for state machine workflows with conditional transitions. Nodes represent states (agent executions or HITL pauses), edges define transitions between states with optional conditional routing. Execution flows from node to node based on edge rules until reaching a terminal node or max_iterations. Useful for decision trees, approval flows, and adaptive workflows.

**Type**: `object`

##### Properties

**`max_iterations`** (*optional*)

- Type: `integer`
- Maximum total node executions to prevent infinite loops in cyclic graphs. Each node execution counts as one iteration. Default: 10. Increase for complex multi-state workflows, decrease for simple decision trees.
- Minimum: `1`
- Default: `10`

**`nodes`** (**required**)

- Type: `object`
- Map of node ID to node configuration. Each node represents a state in the state machine. Node IDs must be valid identifiers (alphanumeric + underscore/hyphen). First node in the map is the entry point for execution.

**`edges`** (**required**)

- Type: `array`
- List of transition rules between nodes. Each edge defines how to move from one node to another, either statically (via 'to') or conditionally (via 'choose'). Edges are evaluated after each node execution to determine next state.

---

### Core Configuration

Essential configuration types used in most workflows.

#### `runtime`

No description available.

**Type**: `object`

##### Properties

**`provider`** (**required**)

- Type: `string`
- LLM provider identifier (e.g., bedrock, openai, azure_openai, danskegpt, local).

**`model_id`** (*optional*)

- Type: `string`
- Default model for agents that don't override.

**`region`** (*optional*)

- Type: `string`
- AWS region for Bedrock provider (e.g., 'us-east-1', 'eu-central-1'). Required when provider is 'bedrock'. Ignored for other providers.

**`host`** (*optional*)

- Type: `string`
- Server host URL for providers like Ollama or OpenAI-compatible servers (e.g., http://localhost:11434).
- Format: `uri`

**`space_id`** (*optional*)

- Type: `string`
- Space identifier for DanskeGPT provider (required when provider is danskegpt).

**`temperature`** (*optional*)

- Type: `number`
- Sampling temperature for generation.
- Minimum: `0.0`
- Maximum: `2.0`

**`top_p`** (*optional*)

- Type: `number`
- Nucleus sampling parameter.
- Minimum: `0.0`
- Maximum: `1.0`

**`max_tokens`** (*optional*)

- Type: `integer`
- Maximum tokens to generate.
- Minimum: `1`

**`max_parallel`** (*optional*)

- Type: `integer`
- Maximum number of concurrent agent invocations in parallel patterns (parallel branches, workflow tasks, orchestrator workers). Controls resource usage and API rate limit management. Default varies by pattern.
- Minimum: `1`
- Default: `5`

**`budgets`** (*optional*)

- Type: `object`
- Resource limits and cost controls for workflow execution. Enforced at runtime with graceful failures and warnings.

**`failure_policy`** (*optional*)

- Type: `object`
- Retry and backoff configuration for transient failures (network errors, rate limits, timeouts). Applied to all agent invocations unless overridden.

---

#### `agents`

Map of agent name -> spec

**Type**: `object`

---

#### `agentSpec`

Agent specification defining behavior, capabilities, and configuration. Each agent has a unique system prompt and can optionally override runtime settings.

**Type**: `object`

##### Properties

**`prompt`** (**required**)

- Type: `string`
- System prompt defining agent role, instructions, and behavioral guidelines. Supports Jinja2 templating to reference input variables (e.g., 'You are a {{role}} specializing in {{domain}}'). This is the core definition of agent identity and capabilities.

**`tools`** (*optional*)

- Type: `array`
- List of tool IDs this agent can use. References tools defined in top-level 'tools' section. Tool IDs can be python callables (e.g., 'strands_tools.http_request'), MCP server IDs, HTTP executor IDs, or native tool names. Empty array or omit for agents without tool access.

**`provider`** (*optional*)

- Type: `string`
- Overrides runtime.provider for this agent. Use to mix providers within workflow (e.g., GPT-4 for reasoning, Claude for writing). Must be one of: 'bedrock', 'openai', 'ollama', 'danskegpt'.

**`model_id`** (*optional*)

- Type: `string`
- Overrides runtime.model_id for this agent. Use to assign different models to different agents based on task requirements (e.g., larger model for complex reasoning, smaller/faster for simple tasks).

**`inference`** (*optional*)

- Type: `object`
- Overrides runtime inference parameters (temperature, top_p, max_tokens) for this agent. Use to fine-tune generation behavior per agent role.

---

#### `tools`

No description available.

**Type**: `object`

##### Properties

**`python`** (*optional*)

- Type: `array`
- Python callable tools imported from modules. MVP supports allowlisted callables (strands_tools.http_request, strands_tools.file_read) and native tools with TOOL_SPEC pattern. Tools must return ToolResult dict with toolUseId, status, and content fields.

**`mcp`** (*optional*)

- Type: `array`

**`http_executors`** (*optional*)

- Type: `array`

---

#### `inputs`

Input parameter definitions for workflow. Specify types, defaults, and validation constraints. Parameters can be passed via --var flags at runtime.

**Type**: `object`

##### Properties

**`required`** (*optional*)

- Type: `object`
- Required input parameters that must be provided via --var flags or have defaults. Workflow fails if required parameters without defaults are missing.

**`optional`** (*optional*)

- Type: `object`
- Optional input parameters that can be omitted. Use with default values or conditional templates (e.g., {{param|default:'fallback'}}).

**`values`** (*optional*)

- Type: `object`
- Actual input values provided at runtime (e.g., via --var flags or defaults). Typically populated by CLI during execution, not manually specified in workflow file.

---

#### `outputs`

No description available.

**Type**: `object`

##### Properties

**`artifacts`** (*optional*)

- Type: `array`

---

#### `env`

Environment configuration for secrets and filesystem mounts. Secrets are injected as environment variables; mounts provide file access to tools.

**Type**: `object`

##### Properties

**`secrets`** (*optional*)

- Type: `array`
- Secret definitions for sensitive data like API keys, tokens, and credentials. Values are never logged or included in telemetry.

**`mounts`** (*optional*)

- Type: `object`
- Logical mount name to local path mappings. Allows tools to access files in specified directories (e.g., 'workspace': '/home/user/project'). Used for file read/write operations.

---

### Advanced Features

Optional advanced configuration for observability, security, and optimization.

#### `telemetry`

OpenTelemetry (OTEL) configuration for distributed tracing and observability. Send spans to OTLP-compatible backends (Jaeger, Honeycomb, Datadog, etc.).

**Type**: `object`

##### Properties

**`otel`** (*optional*)

- Type: `object`
- OTEL exporter configuration. Spans include workflow execution, agent invocations, tool calls, and LLM completions.

**`redact`** (*optional*)

- Type: `object`
- Redaction policies for sensitive data in traces. Prevents PII and credentials from appearing in telemetry backends.

---

#### `contextPolicy`

Context management configuration to control how conversation history and external knowledge are handled during workflow execution. Includes compaction (summarization), persistent notes, and just-in-time retrieval tools.

**Type**: `object`

##### Properties

**`compaction`** (*optional*)

- Type: `object`
- Automatic context window compression via summarization of older messages. Prevents token limit overflow in long-running workflows by condensing conversation history while preserving recent exchanges.

**`notes`** (*optional*)

- Type: `object`
- Persistent notes file for capturing key insights across workflow steps. Agents can write to notes file, and recent notes are automatically included in subsequent agent contexts for cross-step memory.

**`retrieval`** (*optional*)

- Type: `object`
- Configuration for Just-In-Time (JIT) retrieval tools that provide file system access during agent execution.

---

#### `security`

Security policies and restrictions applied to workflow execution. Parsed by CLI but not enforced in MVP - validation only. Future versions will enforce these guardrails at runtime.

**Type**: `object`

##### Properties

**`guardrails`** (*optional*)

- Type: `object`
- Security guardrails to restrict agent capabilities and prevent unsafe operations. Parsed in MVP for validation but not enforced during execution.

---

#### `skills`

Skill bundles that inject domain-specific knowledge or capabilities into agent prompts. Each skill references a directory containing code, docs, or assets. Metadata is injected into system prompt; executable assets planned for future.

**Type**: `array`

---

### Utility Types

Basic types and validators used throughout the schema.

#### `identifier`

Alphanumeric identifier allowing dots, underscores, colons, and hyphens. Used for agent IDs, tool IDs, task IDs, node IDs, and other reference keys throughout the workflow specification.

**Type**: `string`

**Constraints**:

- Pattern: `^[A-Za-z0-9._:-]+$`

**Examples**:

```
writer
```
```
researcher
```
```
gh
```
```
report-1
```

---

#### `inference`

LLM inference parameters controlling generation behavior. Can be specified at runtime level (default for all agents) or per-agent (overrides runtime settings).

**Type**: `object`

##### Properties

**`temperature`** (*optional*)

- Type: `number`
- Sampling temperature (0.0-2.0). Higher values increase randomness/creativity. Lower values make output more deterministic. Typical: 0.7 for creative tasks, 0.1-0.3 for factual/analytical tasks.
- Minimum: `0.0`
- Maximum: `2.0`

**`top_p`** (*optional*)

- Type: `number`
- Nucleus sampling parameter (0.0-1.0). Alternative to temperature. Considers tokens with cumulative probability mass up to top_p. Typical: 0.9-0.95. Use either temperature OR top_p, not both.
- Minimum: `0.0`
- Maximum: `1.0`

**`max_tokens`** (*optional*)

- Type: `integer`
- Maximum tokens to generate in response. Acts as hard limit on output length. Does not include input tokens. Set appropriately for expected output (e.g., 500 for summaries, 2000 for detailed reports).
- Minimum: `1`

---

#### `inputVarMap`

Map of parameter names to type specifications. Keys are parameter names used in Jinja2 templates (e.g., {{param_name}}). Values can be shorthand type strings or detailed specification objects.

**Type**: `object`

---

#### `inputVarSpec`

Input parameter specification. Use shorthand string for simple types (e.g., 'string', 'number') or object format for detailed configuration with descriptions, defaults, and enum constraints.

**Type**: `string` | `object`

---

#### `nonEmptyString`

Non-empty string value with at least one character.

**Type**: `string`

**Constraints**:

- Min length: `1`

---

#### `pattern`

No description available.

**Type**: `object`

##### Properties

**`type`** (**required**)

- Type: `string`
- Allowed values: `chain`, `routing`, `parallel`, `orchestrator_workers`, `evaluator_optimizer`, `graph`, `workflow`

**`config`** (**required**)

- Type: `chainConfig` | `routingConfig` | `parallelConfig` | `orchestratorWorkersConfig` | `evaluatorOptimizerConfig` | `graphConfig` | `workflowConfig`

---

#### `step`

No description available.

**Type**: `object`

---

#### `tag`

Lowercase tag starting with alphanumeric character, allowing dots, hyphens, and underscores in subsequent positions. Used for workflow classification and filtering.

**Type**: `string`

**Constraints**:

- Pattern: `^[a-z0-9][a-z0-9._-]*$`

**Examples**:

```
production
```
```
experimental
```
```
ml-training
```
```
data.processing
```

---

## See Also

- [Workflow Manual](workflow-manual.md) - Comprehensive guide with examples
- [Pattern Explanations](../explanation/patterns.md) - When to use each pattern
- [CLI Reference](cli.md) - Command-line interface
- [Examples](examples.md) - Example workflows for each pattern
- [Tutorials](../tutorials/quickstart-ollama.md) - Getting started guide