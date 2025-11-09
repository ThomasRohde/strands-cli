# Types and Models

Core Pydantic models and type definitions for Strands CLI.

## Overview

All types and models are defined in `strands_cli.types` using Pydantic v2 with strict validation.

## Core Models

::: strands_cli.types
    options:
      show_root_heading: true
      heading_level: 3
      members:
        - Spec
        - Runtime
        - Agent
        - AgentConfig
        - Pattern
        - PatternConfig
        - ChainConfig
        - WorkflowConfig
        - RoutingConfig
        - ParallelConfig
        - EvaluatorOptimizerConfig
        - OrchestratorWorkersConfig
        - GraphConfig
        - RunResult
        - StepResult
        - TaskResult
        - BranchResult
        - NodeResult
