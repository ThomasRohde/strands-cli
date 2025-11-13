# Types and Models

Core Pydantic models and type definitions for Strands CLI.

## Overview

All types and models are defined in `strands_cli.types` using Pydantic v2 with strict validation.

## Enumerations

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - ProviderType
        - PatternType
        - SecretSource
        - ToolType
        - StreamChunkType

## Core Workflow Models

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - Spec
        - Runtime
        - Agent
        - Pattern
        - PatternConfig

## Pattern Step/Task Models

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - ChainStep
        - WorkflowTask
        - HITLStep
        - Route
        - ParallelBranch
        - GraphNode
        - GraphEdge

## Tool Models

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - PythonTool
        - HttpExecutor
        - McpServer

## Configuration Models

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - Secret
        - Skill
        - Artifact
        - Outputs
        - RouterConfig
        - EvaluatorConfig
        - AcceptConfig
        - WorkerTemplate
        - OrchestratorConfig
        - OrchestratorLimits

## Result Models

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - RunResult
        - StreamChunk

## Capability Analysis

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - CapabilityReport
        - CapabilityIssue
