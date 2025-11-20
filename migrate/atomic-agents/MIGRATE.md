# Feature Migration: atomic-agents

**Generated**: 2025-11-20 07:14:45  
**Source Branch**: master  
**Source Commit**: eba372be6b57ceacbb5af513b508717a76c37862

## Overview

This migration package contains the **Atomic Agents** feature for Strands CLI - a comprehensive framework for single-purpose, reusable agents with explicit input/output contracts.

### Changed Files Summary

**Modified Files (15)**:
- `CHANGELOG.md` - Added atomic agents feature to Unreleased section
- `README.md` - Added atomic agents section to features
- `docs/ATOMIC_AGENTS.md` - Comprehensive atomic agents PRD and design document
- `manual/SUMMARY.md` - Added atomic agents documentation links
- `manual/explanation/patterns.md` - Added atomic agents integration with patterns
- `manual/index.md` - Added atomic agents to features list
- `manual/reference/cli.md` - Added `strands atomic` command documentation
- `manual/reference/spec.md` - Added agent reference support ($ref)
- `mkdocs.yml` - Added atomic agents navigation entries
- `src/strands_cli/__main__.py` - Integrated atomic CLI commands
- `src/strands_cli/loader/yaml_loader.py` - Added agent $ref resolution
- `src/strands_cli/schema/strands-workflow.schema.json` - Added agent reference schema support
- `src/strands_cli/types.py` - Added Agent.ref field with Pydantic aliasing
- `tests/conftest.py` - Added atomic agent test fixtures
- `tests/test_async_context.py` - Added async context preservation tests

**New Directories (3)**:
- `agents/atomic/` - Atomic agent library (3 example agents with schemas and tests)
- `src/strands_cli/atomic/` - Atomic agents CLI and core functionality
- `examples/data/` - Test data for atomic agent examples

**New Files (12)**:
- `examples/atomic-ref-demo-openai.yaml` - Atomic agent reference demo
- `examples/classify_emails_e2e.py` - End-to-end email classification example
- `examples/customer-support-intake-composite-openai.yaml` - Composite workflow using atomic agents
- `examples/test_customer_support_intake.py` - Test script for composite workflow
- `manual/explanation/atomic-agents.md` - Design philosophy and architecture
- `manual/howto/atomic-agents.md` - How-to guide for working with atomic agents
- `manual/reference/atomic-quick-reference.md` - Quick reference for atomic agents
- `manual/tutorials/atomic-agents.md` - Tutorial for getting started
- `tests/test_agent_references.py` - Tests for agent $ref resolution (8 tests)
- `tests/test_atomic_cli.py` - Tests for atomic CLI commands
- `tests/test_atomic_detection.py` - Tests for atomic agent discovery
- `tests/test_schema_metadata_and_contracts.py` - Tests for metadata and contract validation

## Integration Instructions

### Prerequisites

1. Ensure target repository is on a clean branch
2. Review all files in `files/` directory before applying
3. Back up target repository or create a new branch:
   ```bash
   git checkout -b integrate-atomic-agents
   ```

### High-Level Overview

The **Atomic Agents** feature adds:

1. **CLI Commands** (`strands atomic ...`):
   - `list` - Discover atomic agents in repository
   - `describe` - Show agent metadata and contracts
   - `run` - Execute agent with input/output validation
   - `test` - Run test suite for agent
   - `init` - Scaffold new atomic agent with templates
   - `validate` - Check atomic invariants

2. **Agent Composition** (`$ref` in agent definitions):
   - Reference external atomic agent specs in composite workflows
   - Override model_id, provider, tools, and inference parameters
   - Automatic schema path resolution relative to atomic agent file
   - Circular reference detection

3. **Directory Structure**:
   - `agents/atomic/<name>/` - Self-contained atomic agents
   - Each with `<name>.yaml`, `schemas/`, `examples/`, `tests.yaml`

4. **Documentation**:
   - Complete manual sections for tutorials, how-to, explanation, and reference
   - Integration with existing workflow patterns documentation

### File-by-File Integration

---

#### Modified Files

---

#### File: `CHANGELOG.md`

**Status**: modified

**Target Location**: `CHANGELOG.md` (root)

**Integration Steps**:

1. **Key changes**: Added new `[Unreleased]` section with comprehensive atomic agents feature description

2. **Integration approach**:
   
   ```bash
   # Safe replacement - prepend new [Unreleased] section above existing entries
   ```
   
   - Open both files side-by-side
   - Copy the new `[Unreleased]` section from migration file
   - Paste at the top of the CHANGELOG (above existing version entries)
   - Ensure proper Markdown formatting maintained

3. **Verification**:
   ```bash
   # Check CHANGELOG structure
   head -30 CHANGELOG.md
   # Should show new [Unreleased] section with atomic agents feature
   ```

---

#### File: `README.md`

**Status**: modified

**Target Location**: `README.md` (root)

**Integration Steps**:

1. **Key changes**:
   - Added "Atomic Agents" bullet to "Key Features" section
   - Added "Atomic Agents" section with CLI commands and examples
   - Updated documentation structure to reference atomic agents

2. **Integration approach**:
   
   **Option A - Safe replacement** (if target README is identical to pre-atomic version):
   ```bash
   Copy-Item "./migrate/atomic-agents/files/README.md" "README.md" -Force
   ```
   
   **Option B - Manual merge** (recommended if target has diverged):
   - Open both files side-by-side
   - Find "Key Features" section and add:
     ```markdown
     🧩 **Atomic Agents**
     - Reusable single-purpose agents with explicit input/output contracts
     - Dedicated CLI commands: `strands atomic list/describe/run/test/init`
     - Auto-discovery via metadata labels
     - Built-in test framework with fixture-based testing
     - Compose into workflows as building blocks
     ```
   - Find appropriate section (after "CLI Commands" or before "Documentation") and add full "Atomic Agents" section from migration file (search for "## Atomic Agents")

3. **Verification**:
   ```bash
   # Check atomic agents CLI documentation
   Select-String -Path README.md -Pattern "strands atomic"
   # Should show CLI command examples
   ```

---

#### File: `docs/ATOMIC_AGENTS.md`

**Status**: modified

**Target Location**: `docs/ATOMIC_AGENTS.md`

**Integration Steps**:

1. **Key changes**: Complete PRD and design document for atomic agents concept

2. **Integration approach**:
   
   ```bash
   # Safe replacement - this is a comprehensive design document
   Copy-Item "./migrate/atomic-agents/files/docs/ATOMIC_AGENTS.md" "docs/ATOMIC_AGENTS.md" -Force
   ```

3. **Verification**:
   ```bash
   # Verify document structure
   Get-Content docs/ATOMIC_AGENTS.md | Select-String "^## " | Select-Object -First 10
   # Should show: Overview, Goals & Non-Goals, Concept & Terminology, etc.
   ```

---

#### File: `manual/SUMMARY.md`

**Status**: modified

**Target Location**: `manual/SUMMARY.md`

**Integration Steps**:

1. **Key changes**: Added atomic agents documentation links to navigation

2. **Integration approach**:
   
   ```bash
   # Safe replacement - adds new navigation entries
   Copy-Item "./migrate/atomic-agents/files/manual/SUMMARY.md" "manual/SUMMARY.md" -Force
   ```
   
   **Verify additions**:
   - Tutorials: `- [Atomic Agents](tutorials/atomic-agents.md)`
   - How-To: `- [Work with Atomic Agents](howto/atomic-agents.md)`
   - Explanation: `- [Atomic Agents](explanation/atomic-agents.md)`
   - Reference: `- [Atomic Agents Quick Reference](reference/atomic-quick-reference.md)`

3. **Verification**:
   ```bash
   # Check for atomic agents entries
   Select-String -Path manual/SUMMARY.md -Pattern "atomic"
   # Should show 4+ matches
   ```

---

#### File: `manual/explanation/patterns.md`

**Status**: modified

**Target Location**: `manual/explanation/patterns.md`

**Integration Steps**:

1. **Key changes**: Added "Patterns and Atomic Agents" section showing integration between atomic agents and all 7 workflow patterns

2. **Integration approach**:
   
   ```bash
   # Safe replacement if target hasn't diverged
   Copy-Item "./migrate/atomic-agents/files/manual/explanation/patterns.md" "manual/explanation/patterns.md" -Force
   ```
   
   **Manual merge** (if needed):
   - Scroll to end of file (before "## Summary")
   - Add new section "## Patterns and Atomic Agents" from migration file
   - Content includes examples for Chain, Workflow, Orchestrator, and Graph patterns

2. **Verification**:
   ```bash
   # Check for new section
   Select-String -Path manual/explanation/patterns.md -Pattern "Patterns and Atomic Agents"
   # Should find section header
   ```

---

#### File: `manual/index.md`

**Status**: modified

**Target Location**: `manual/index.md`

**Integration Steps**:

1. **Key changes**: Added atomic agents to "Key Features" list

2. **Integration approach**:
   
   ```bash
   # Safe replacement - adds one bullet point
   Copy-Item "./migrate/atomic-agents/files/manual/index.md" "manual/index.md" -Force
   ```
   
   **Manual merge** (if needed):
   - Find "Key Features" section
   - Add after "Context Management":
     ```markdown
     - **Atomic Agents**: Dedicated `strands atomic` commands for listing, describing, running, testing, and scaffolding single-purpose agents with input/output contracts
     ```

3. **Verification**:
   ```bash
   # Check for atomic agents feature
   Select-String -Path manual/index.md -Pattern "Atomic Agents"
   ```

---

#### File: `manual/reference/cli.md`

**Status**: modified

**Target Location**: `manual/reference/cli.md`

**Integration Steps**:

1. **Key changes**: Added comprehensive `strands atomic` command documentation (list, describe, run, test, init, validate)

2. **Integration approach**:
   
   **Option A - Safe replacement** (if target CLI docs haven't diverged):
   ```bash
   Copy-Item "./migrate/atomic-agents/files/manual/reference/cli.md" "manual/reference/cli.md" -Force
   ```
   
   **Option B - Manual merge** (recommended):
   - Find "## Commands" section
   - Add new subsection after global options:
     ```markdown
     ### atomic (subcommands)

     Work with atomic agent manifests (single-agent specs with contracts).

     - `strands atomic list [--all] [--json]` — discover atomic manifests in the repo.
     - `strands atomic describe <name> [--format json|yaml]` — show metadata, labels, contracts.
     - `strands atomic validate <name>` — check atomic invariants and contract file existence.
     - `strands atomic run <name> --input-file <path> [--output-file <path>]` — execute with input/output schema validation.
     - `strands atomic test <name> [--filter <pattern>] [--json]` — run `_tests.yaml` cases.
     - `strands atomic init <name> [--domain ...] [--capability ...] [--force]` — scaffold manifest + schemas + tests + sample input.
     ```

3. **Verification**:
   ```bash
   # Check for atomic commands
   Select-String -Path manual/reference/cli.md -Pattern "strands atomic"
   # Should show multiple command examples
   ```

---

#### File: `manual/reference/spec.md`

**Status**: modified

**Target Location**: `manual/reference/spec.md`

**Integration Steps**:

1. **Key changes**: Added agent reference support (`$ref`) documentation in "Agents" section

2. **Integration approach**:
   
   **Manual merge** (complex changes):
   - Find "## Agents" section
   - Update section header to:
     ```markdown
     ## Agents

     Agent definitions with prompts, tools, and overrides. Supports both inline definitions and references to external atomic agents.

     ### Inline Agent Definition
     ```
   - Add new subsection after inline agent table:
     ```markdown
     ### Agent Reference ($ref)

     Reference external atomic agent specs for composition and reuse.

     ```yaml
     agents:
       classifier:
         $ref: ./agents/atomic/classify_ticket_priority/classify_ticket_priority.yaml#/agents/classify_ticket_priority
         tools: ["http_request"]  # Override tools
         model_id: "gpt-4o"  # Override model
     ```

     | Field | Type | Description |
     |-------|------|-------------|
     | `$ref` | string | Path to atomic agent spec + JSONPointer to agent definition |
     | `tools` | array[string] | Tool override (replaces referenced agent's tools) |
     | `model_id` | string | Model override |
     | `provider` | string | Provider override |
     | `inference` | object | Inference parameter overrides |

     **Path Resolution**:
     - Paths are relative to the **composite workflow** file (not the atomic agent file)
     - JSONPointer (`#/agents/agent_id`) selects specific agent from referenced spec
     - Schema paths in referenced agent are resolved relative to **atomic agent file**

     **Constraints**:
     - No circular references (A → B → A)
     - No nested references (A → B → C, where both A and B use $ref)
     - Referenced agent must pass atomic invariant checks
     ```

3. **Verification**:
   ```bash
   # Check for $ref documentation
   Select-String -Path manual/reference/spec.md -Pattern '\$ref'
   ```

---

#### File: `mkdocs.yml`

**Status**: modified

**Target Location**: `mkdocs.yml`

**Integration Steps**:

1. **Key changes**: Added atomic agents navigation entries across Tutorials, How-To, Explanation, and Reference sections

2. **Integration approach**:
   
   ```bash
   # Safe replacement - adds navigation entries
   Copy-Item "./migrate/atomic-agents/files/mkdocs.yml" "mkdocs.yml" -Force
   ```
   
   **Verify navigation additions**:
   - Under `Tutorials`: `- Atomic Agents: tutorials/atomic-agents.md`
   - Under `How-To`: `- Work with Atomic Agents: howto/atomic-agents.md`
   - Under `Explanation`: `- Atomic Agents: explanation/atomic-agents.md`
   - Under `Reference`: `- Atomic Agents Quick Reference: reference/atomic-quick-reference.md`

3. **Verification**:
   ```bash
   # Check navigation structure
   Select-String -Path mkdocs.yml -Pattern "atomic-agents.md"
   # Should show 4 entries
   ```

---

#### File: `src/strands_cli/__main__.py`

**Status**: modified

**Target Location**: `src/strands_cli/__main__.py`

**Integration Steps**:

1. **Key changes**:
   - **New import**: `from strands_cli.atomic.cli import atomic_app`
   - **CLI integration**: `app.add_typer(atomic_app, name="atomic")`
   - Added around line 168 (after app instantiation)

2. **Integration approach**:
   
   **Manual merge** (precise location matters for imports):
   
   a. **Add import** (around line 41, with other local imports):
   ```python
   from strands_cli.atomic.cli import atomic_app
   ```
   
   b. **Register subcommand** (around line 168, after `app = typer.Typer(...)`):
   ```python
   console = Console()
   app.add_typer(atomic_app, name="atomic")
   ```

3. **Verification**:
   ```python
   # Test CLI integration
   uv run strands atomic --help
   # Should show atomic subcommands: list, describe, run, test, init, validate
   ```

---

#### File: `src/strands_cli/loader/yaml_loader.py`

**Status**: modified

**Target Location**: `src/strands_cli/loader/yaml_loader.py`

**Integration Steps**:

1. **Key changes**:
   - **New function**: `_resolve_agent_references(spec_data: dict[str, Any], spec_path: Path) -> None`
   - Resolves `$ref` in agent definitions before schema validation
   - Handles path resolution relative to composite workflow
   - Schema paths in referenced agents resolved relative to atomic agent file
   - Circular reference detection
   
2. **Integration approach**:
   
   **Manual merge** (add new function and call site):
   
   a. **Add function** (around line 200, before `load_spec`):
   ```python
   def _resolve_agent_references(spec_data: dict[str, Any], spec_path: Path) -> None:
       """Resolve agent references ($ref) in spec_data.agents.
       
       This enables atomic agent composition: reference external agent specs
       and override specific fields (tools, model_id, inference).
       
       Args:
           spec_data: Spec dictionary to modify in-place
           spec_path: Path to the composite workflow (for relative path resolution)
           
       Raises:
           LoadError: If $ref is invalid, circular, or references missing file
       """
       debug = os.environ.get("STRANDS_DEBUG", "").lower() == "true"
       
       if "agents" not in spec_data or not isinstance(spec_data["agents"], dict):
           return
       
       seen_refs: set[str] = set()
       
       for agent_id, agent_def in spec_data["agents"].items():
           if not isinstance(agent_def, dict):
               continue
           
           ref_path = agent_def.get("$ref") or agent_def.get("ref")
           if not ref_path:
               continue
           
           if ref_path in seen_refs:
               raise LoadError(f"Circular reference detected: {ref_path}")
           seen_refs.add(ref_path)
           
           if debug:
               logger.debug("resolving_agent_ref", agent_id=agent_id, ref=ref_path)
           
           # Parse $ref: path/to/file.yaml#/agents/agent_name
           parts = ref_path.split("#", 1)
           file_path_str = parts[0]
           json_pointer = parts[1] if len(parts) > 1 else None
           
           # Resolve path relative to composite workflow
           ref_file = Path(file_path_str)
           if not ref_file.is_absolute():
               ref_file = (spec_path.parent / file_path_str).resolve()
           
           if not ref_file.exists():
               raise LoadError(f"Agent reference not found: {ref_file}")
           
           # Load referenced spec
           yaml = YAML(typ="safe", pure=True)
           try:
               ref_spec_data = yaml.load(ref_file.read_text(encoding="utf-8"))
           except Exception as e:
               raise LoadError(f"Failed to parse referenced spec {ref_file}: {e}") from e
           
           if not isinstance(ref_spec_data, dict):
               raise LoadError(f"Referenced spec must be a dict, got {type(ref_spec_data)}")
           
           # Extract agent definition via JSONPointer
           if json_pointer:
               parts = [p for p in json_pointer.split("/") if p]
               target = ref_spec_data
               for part in parts:
                   if not isinstance(target, dict) or part not in target:
                       raise LoadError(f"JSONPointer {json_pointer} not found in {ref_file}")
                   target = target[part]
               referenced_agent = target
           else:
               # No pointer: assume single-agent spec
               agents = ref_spec_data.get("agents")
               if not isinstance(agents, dict) or len(agents) != 1:
                   raise LoadError(f"Reference {ref_file} must have exactly one agent or use JSONPointer")
               referenced_agent = next(iter(agents.values()))
           
           if not isinstance(referenced_agent, dict):
               raise LoadError(f"Referenced agent must be a dict, got {type(referenced_agent)}")
           
           # Check for nested references (not allowed)
           if "$ref" in referenced_agent or "ref" in referenced_agent:
               raise LoadError(f"Nested agent references not allowed: {ref_path}")
           
           # Resolve schema paths relative to atomic agent file (not composite workflow)
           for schema_field in ["input_schema", "output_schema"]:
               schema_ref = referenced_agent.get(schema_field)
               if isinstance(schema_ref, str):
                   schema_path = Path(schema_ref)
                   if not schema_path.is_absolute():
                       # Resolve relative to atomic agent file
                       resolved_schema = (ref_file.parent / schema_ref).resolve()
                       referenced_agent[schema_field] = str(resolved_schema)
           
           # Merge: referenced agent as base, override fields from composite spec
           merged_agent = referenced_agent.copy()
           
           # Allow overrides: tools, model_id, provider, inference
           override_fields = ["tools", "model_id", "provider", "inference"]
           for field in override_fields:
               if field in agent_def and field != "$ref" and field != "ref":
                   merged_agent[field] = agent_def[field]
           
           spec_data["agents"][agent_id] = merged_agent
           
           if debug:
               logger.debug(
                   "resolved_agent_ref",
                   agent_id=agent_id,
                   ref=ref_path,
                   resolved_file=str(ref_file),
                   overrides={k: v for k, v in agent_def.items() if k in override_fields},
               )
   ```
   
   b. **Call before schema validation** (in `load_spec` function, around line 260):
   ```python
   def load_spec(file_path: str | Path, variables: dict[str, str] | None = None) -> Spec:
       """Load and validate a workflow spec from YAML or JSON."""
       file_path_obj = Path(file_path)
       _validate_file_path(file_path_obj)
       
       content = file_path_obj.read_text(encoding="utf-8")
       spec_data = _parse_file_content(file_path_obj, content)
       
       # NEW: Resolve agent references BEFORE schema validation
       _resolve_agent_references(spec_data, file_path_obj)
       
       _apply_input_defaults(spec_data)
       
       if variables:
           _merge_variables(spec_data, variables)
       
       # Continue with validation...
   ```

3. **Verification**:
   ```python
   # Test agent reference resolution
   uv run strands validate examples/customer-support-intake-composite-openai.yaml
   # Should validate successfully with resolved agent references
   ```

---

#### File: `src/strands_cli/schema/strands-workflow.schema.json`

**Status**: modified

**Target Location**: `src/strands_cli/schema/strands-workflow.schema.json`

**Integration Steps**:

1. **Key changes**:
   - Updated agent definition to support `oneOf` pattern:
     - Inline agent definition (prompt + tools + ...)
     - Agent reference ($ref with optional overrides)
   - Added `$ref` property with string type
   - Added metadata.labels for atomic agent markers
   - Added input_schema and output_schema fields to agent definition

2. **Integration approach**:
   
   ```bash
   # Safe replacement - schema changes are additive and backward-compatible
   Copy-Item "./migrate/atomic-agents/files/src/strands_cli/schema/strands-workflow.schema.json" "src/strands_cli/schema/strands-workflow.schema.json" -Force
   ```
   
   **Key schema additions**:
   ```json
   "Agent": {
     "oneOf": [
       {
         "type": "object",
         "properties": {
           "prompt": {"type": "string"},
           "tools": {"type": "array"},
           "input_schema": {"oneOf": [{"type": "string"}, {"type": "object"}]},
           "output_schema": {"oneOf": [{"type": "string"}, {"type": "object"}]}
         },
         "required": ["prompt"]
       },
       {
         "type": "object",
         "properties": {
           "$ref": {"type": "string"},
           "tools": {"type": "array"},
           "model_id": {"type": "string"},
           "provider": {"type": "string"},
           "inference": {"type": "object"}
         },
         "required": ["$ref"]
       }
     ]
   }
   ```

3. **Verification**:
   ```bash
   # Validate schema file itself
   python -c "import json; json.load(open('src/strands_cli/schema/strands-workflow.schema.json'))"
   # Should parse without errors
   ```

---

#### File: `src/strands_cli/types.py`

**Status**: modified

**Target Location**: `src/strands_cli/types.py`

**Integration Steps**:

1. **Key changes**:
   - **Agent model**: Added `ref` field with Pydantic `Field(alias="$ref")` for JSON Schema compatibility
   - **Agent model**: Added `input_schema` and `output_schema` fields (str | dict | None)
   - **Metadata model**: Added `labels: dict[str, str] | None` for atomic agent markers

2. **Integration approach**:
   
   **Manual merge** (find Agent class definition around line 400):
   
   a. **Update Metadata class** (around line 230):
   ```python
   class Metadata(BaseModel):
       """Optional metadata for workflow and agent manifests."""
       
       name: str | None = None
       description: str | None = None
       labels: dict[str, str] | None = None  # NEW: for atomic agent labels
   ```
   
   b. **Update Agent class** (around line 400):
   ```python
   class Agent(BaseModel):
       """Agent configuration with prompt and optional tool overrides."""
       
       # NEW: Agent reference for composition
       ref: str | None = Field(None, alias="$ref", description="Reference to external agent spec")
       
       prompt: str | None = None
       tools: list[str] | None = None
       provider: ProviderType | None = None
       model_id: str | None = None
       inference: dict[str, Any] | None = None
       
       # NEW: Contract schemas for atomic agents
       input_schema: str | dict[str, Any] | None = None
       output_schema: str | dict[str, Any] | None = None
       
       @model_validator(mode="after")
       def check_prompt_or_ref(self) -> "Agent":
           """Ensure either prompt or ref is present."""
           if not self.prompt and not self.ref:
               raise ValueError("Agent must have either 'prompt' or '$ref'")
           return self
   ```

3. **Verification**:
   ```python
   # Test Pydantic model changes
   uv run pytest tests/test_schema_metadata_and_contracts.py -v
   # Should pass all tests
   ```

---

#### File: `tests/conftest.py`

**Status**: modified

**Target Location**: `tests/conftest.py`

**Integration Steps**:

1. **Key changes**:
   - Added atomic agent test fixtures:
     - `atomic_agent_spec` - Valid atomic agent YAML
     - `atomic_agent_with_ref` - Composite workflow using $ref
     - `temp_atomic_agent_file` - Temporary atomic agent file for testing

2. **Integration approach**:
   
   **Manual merge** (add new fixtures at end of file):
   
   ```python
   # Add after existing fixtures (around line 300+):
   
   @pytest.fixture
   def atomic_agent_spec() -> dict[str, Any]:
       """Valid atomic agent specification."""
       return {
           "version": 0,
           "name": "test_atomic_agent",
           "runtime": {"provider": "ollama", "model_id": "llama2", "host": "http://localhost:11434"},
           "agents": {
               "test_agent": {
                   "prompt": "You are a test agent",
                   "input_schema": {"type": "object", "properties": {"input": {"type": "string"}}},
                   "output_schema": {"type": "object", "properties": {"output": {"type": "string"}}}
               }
           },
           "metadata": {
               "labels": {
                   "strands.io/agent_type": "atomic",
                   "strands.io/domain": "testing",
                   "strands.io/capability": "echo"
               }
           },
           "pattern": {
               "type": "chain",
               "config": {"steps": [{"agent": "test_agent", "input": "Test input"}]}
           }
       }
   
   @pytest.fixture
   def atomic_agent_with_ref(tmp_path: Path) -> tuple[Path, Path]:
       """Create atomic agent and composite workflow with $ref."""
       # Create atomic agent
       atomic_dir = tmp_path / "agents" / "atomic" / "test_agent"
       atomic_dir.mkdir(parents=True)
       
       atomic_spec = {
           "version": 0,
           "name": "test_atomic_agent",
           "runtime": {"provider": "ollama", "model_id": "llama2"},
           "agents": {
               "test_agent": {
                   "prompt": "You are a test agent",
                   "input_schema": "./schemas/input.json",
                   "output_schema": "./schemas/output.json"
               }
           },
           "metadata": {
               "labels": {"strands.io/agent_type": "atomic"}
           },
           "pattern": {
               "type": "chain",
               "config": {"steps": [{"agent": "test_agent", "input": "{{ input }}"}]}
           }
       }
       
       atomic_path = atomic_dir / "test_agent.yaml"
       yaml = YAML()
       yaml.dump(atomic_spec, atomic_path)
       
       # Create schemas
       schemas_dir = atomic_dir / "schemas"
       schemas_dir.mkdir()
       (schemas_dir / "input.json").write_text('{"type": "object"}')
       (schemas_dir / "output.json").write_text('{"type": "object"}')
       
       # Create composite workflow
       composite_spec = {
           "version": 0,
           "name": "composite_workflow",
           "runtime": {"provider": "ollama", "model_id": "llama2"},
           "agents": {
               "referenced": {
                   "$ref": "./agents/atomic/test_agent/test_agent.yaml#/agents/test_agent",
                   "tools": ["http_request"]  # Override
               }
           },
           "pattern": {
               "type": "chain",
               "config": {"steps": [{"agent": "referenced", "input": "Test"}]}
           }
       }
       
       composite_path = tmp_path / "composite.yaml"
       yaml.dump(composite_spec, composite_path)
       
       return atomic_path, composite_path
   ```

3. **Verification**:
   ```python
   # Test fixtures
   uv run pytest tests/test_agent_references.py -v
   # Should pass all reference resolution tests
   ```

---

#### File: `tests/test_async_context.py`

**Status**: modified

**Target Location**: `tests/test_async_context.py`

**Integration Steps**:

1. **Key changes**: Added tests for async context preservation across agent reference resolution

2. **Integration approach**:
   
   ```bash
   # Safe replacement - adds new test cases
   Copy-Item "./migrate/atomic-agents/files/tests/test_async_context.py" "tests/test_async_context.py" -Force
   ```

3. **Verification**:
   ```bash
   # Run async context tests
   uv run pytest tests/test_async_context.py -v
   # Should pass all tests
   ```

---

#### New Directories and Files

---

#### Directory: `agents/atomic/`

**Status**: new

**Target Location**: `agents/atomic/`

**Integration Steps**:

1. **Purpose**: Atomic agent library with 3 example agents (each self-contained with schemas, examples, tests)

2. **Integration approach**:
   
   ```bash
   # Copy entire directory structure
   Copy-Item -Path "./migrate/atomic-agents/files/agents/atomic" -Destination "agents/" -Recurse -Force
   ```
   
   **Contents**:
   - `classify_from_summary/` - Classifier agent with input/output schemas
   - `classify_ticket_priority/` - Ticket priority classifier
   - `summarize_customer_email/` - Email summarization agent
   
   Each contains:
   - `<name>.yaml` - Agent manifest
   - `schemas/input.json` - Input JSON Schema
   - `schemas/output.json` - Output JSON Schema
   - `examples/sample.json` - Example input
   - `tests.yaml` - Test suite

3. **Verification**:
   ```bash
   # List atomic agents
   uv run strands atomic list
   # Should show 3 atomic agents
   
   # Describe an agent
   uv run strands atomic describe summarize_customer_email
   # Should show metadata, schemas, and contracts
   ```

---

#### Directory: `src/strands_cli/atomic/`

**Status**: new

**Target Location**: `src/strands_cli/atomic/`

**Integration Steps**:

1. **Purpose**: Atomic agents CLI and core functionality

2. **Integration approach**:
   
   ```bash
   # Copy entire module
   Copy-Item -Path "./migrate/atomic-agents/files/src/strands_cli/atomic" -Destination "src/strands_cli/" -Recurse -Force
   ```
   
   **Files**:
   - `__init__.py` - Module exports
   - `cli.py` - Typer commands (list, describe, run, test, init, validate)
   - `core.py` - Discovery and invariant checking logic

3. **Verification**:
   ```python
   # Test imports
   python -c "from strands_cli.atomic.cli import atomic_app; print('OK')"
   # Should print: OK
   
   # Test CLI
   uv run strands atomic --help
   # Should show subcommands
   ```

---

#### Directory: `examples/data/`

**Status**: new

**Target Location**: `examples/data/`

**Integration Steps**:

1. **Purpose**: Test data for atomic agent examples (email samples)

2. **Integration approach**:
   
   ```bash
   # Copy data directory
   Copy-Item -Path "./migrate/atomic-agents/files/examples/data" -Destination "examples/" -Recurse -Force
   ```

3. **Verification**:
   ```bash
   # Check data files
   Get-ChildItem examples/data
   # Should show email sample files
   ```

---

#### File: `examples/atomic-ref-demo-openai.yaml`

**Status**: new

**Target Location**: `examples/atomic-ref-demo-openai.yaml`

**Integration Steps**:

1. **Purpose**: Demonstration of atomic agent $ref composition

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/examples/atomic-ref-demo-openai.yaml" "examples/" -Force
   ```

3. **Verification**:
   ```bash
   # Validate example
   uv run strands validate examples/atomic-ref-demo-openai.yaml
   # Should validate successfully
   ```

---

#### File: `examples/classify_emails_e2e.py`

**Status**: new

**Target Location**: `examples/classify_emails_e2e.py`

**Integration Steps**:

1. **Purpose**: End-to-end Python example for email classification

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/examples/classify_emails_e2e.py" "examples/" -Force
   ```

3. **Verification**:
   ```bash
   # Test example (requires OpenAI API key)
   uv run python examples/classify_emails_e2e.py
   # Should classify sample emails
   ```

---

#### File: `examples/customer-support-intake-composite-openai.yaml`

**Status**: new

**Target Location**: `examples/customer-support-intake-composite-openai.yaml`

**Integration Steps**:

1. **Purpose**: Real-world composite workflow using 3 atomic agents via $ref

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/examples/customer-support-intake-composite-openai.yaml" "examples/" -Force
   ```

3. **Verification**:
   ```bash
   # Validate composite workflow
   uv run strands validate examples/customer-support-intake-composite-openai.yaml
   # Should resolve all $ref and validate
   ```

---

#### File: `examples/test_customer_support_intake.py`

**Status**: new

**Target Location**: `examples/test_customer_support_intake.py`

**Integration Steps**:

1. **Purpose**: Test script for customer support intake composite workflow

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/examples/test_customer_support_intake.py" "examples/" -Force
   ```

3. **Verification**:
   ```bash
   # Run test (requires OpenAI API key)
   uv run python examples/test_customer_support_intake.py
   # Should execute workflow with atomic agents
   ```

---

#### File: `manual/explanation/atomic-agents.md`

**Status**: new

**Target Location**: `manual/explanation/atomic-agents.md`

**Integration Steps**:

1. **Purpose**: Comprehensive design philosophy and architecture documentation (525 lines)

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/manual/explanation/atomic-agents.md" "manual/explanation/" -Force
   ```

3. **Verification**:
   ```bash
   # Check file
   Get-Content manual/explanation/atomic-agents.md | Measure-Object -Line
   # Should show ~525 lines
   ```

---

#### File: `manual/howto/atomic-agents.md`

**Status**: new

**Target Location**: `manual/howto/atomic-agents.md`

**Integration Steps**:

1. **Purpose**: How-to guide for working with atomic agents (CLI commands, testing, scaffolding)

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/manual/howto/atomic-agents.md" "manual/howto/" -Force
   ```

3. **Verification**:
   ```bash
   Get-Content manual/howto/atomic-agents.md | Select-String "^## "
   # Should show section headers: Discovery, Creating, Testing, etc.
   ```

---

#### File: `manual/reference/atomic-quick-reference.md`

**Status**: new

**Target Location**: `manual/reference/atomic-quick-reference.md`

**Integration Steps**:

1. **Purpose**: Quick reference cheat sheet for atomic agents

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/manual/reference/atomic-quick-reference.md" "manual/reference/" -Force
   ```

3. **Verification**:
   ```bash
   # Check quick reference structure
   Get-Content manual/reference/atomic-quick-reference.md | Select-String "^### "
   # Should show CLI commands, directory structure, etc.
   ```

---

#### File: `manual/tutorials/atomic-agents.md`

**Status**: new

**Target Location**: `manual/tutorials/atomic-agents.md`

**Integration Steps**:

1. **Purpose**: Step-by-step tutorial for building first atomic agent

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/manual/tutorials/atomic-agents.md" "manual/tutorials/" -Force
   ```

3. **Verification**:
   ```bash
   # Check tutorial sections
   Get-Content manual/tutorials/atomic-agents.md | Select-String "^## "
   # Should show: Prerequisites, Your First Atomic Agent, Testing, etc.
   ```

---

#### File: `tests/test_agent_references.py`

**Status**: new

**Target Location**: `tests/test_agent_references.py`

**Integration Steps**:

1. **Purpose**: Comprehensive tests for agent $ref resolution (8 tests covering happy path, overrides, errors, circular refs)

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/tests/test_agent_references.py" "tests/" -Force
   ```

3. **Verification**:
   ```bash
   # Run agent reference tests
   uv run pytest tests/test_agent_references.py -v
   # Should show 8 passed tests
   ```

---

#### File: `tests/test_atomic_cli.py`

**Status**: new

**Target Location**: `tests/test_atomic_cli.py`

**Integration Steps**:

1. **Purpose**: Tests for atomic CLI commands (list, describe, run, test, init, validate)

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/tests/test_atomic_cli.py" "tests/" -Force
   ```

3. **Verification**:
   ```bash
   # Run CLI tests
   uv run pytest tests/test_atomic_cli.py -v
   # Should pass all CLI command tests
   ```

---

#### File: `tests/test_atomic_detection.py`

**Status**: new

**Target Location**: `tests/test_atomic_detection.py`

**Integration Steps**:

1. **Purpose**: Tests for atomic agent discovery logic (auto-discovery via labels and directory structure)

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/tests/test_atomic_detection.py" "tests/" -Force
   ```

3. **Verification**:
   ```bash
   # Run detection tests
   uv run pytest tests/test_atomic_detection.py -v
   # Should pass all discovery tests
   ```

---

#### File: `tests/test_schema_metadata_and_contracts.py`

**Status**: new

**Target Location**: `tests/test_schema_metadata_and_contracts.py`

**Integration Steps**:

1. **Purpose**: Tests for metadata labels and contract validation (input/output schemas)

2. **Integration approach**:
   
   ```bash
   Copy-Item "./migrate/atomic-agents/files/tests/test_schema_metadata_and_contracts.py" "tests/" -Force
   ```

3. **Verification**:
   ```bash
   # Run schema tests
   uv run pytest tests/test_schema_metadata_and_contracts.py -v
   # Should validate Pydantic models and schema constraints
   ```

---

### Dependencies & Configuration

**No new Python dependencies required**. Atomic agents feature uses existing dependencies:
- `typer` (CLI framework)
- `pydantic` (data validation)
- `jsonschema` (contract validation)
- `ruamel.yaml` (YAML parsing)
- `rich` (terminal output)

**No configuration file changes needed** beyond those already captured in file integration above.

---

### Testing Strategy

After integration, run the following tests:

1. **Unit Tests**:
   ```bash
   # Test agent reference resolution
   uv run pytest tests/test_agent_references.py -v
   
   # Test atomic CLI commands
   uv run pytest tests/test_atomic_cli.py -v
   
   # Test atomic detection
   uv run pytest tests/test_atomic_detection.py -v
   
   # Test schema and contracts
   uv run pytest tests/test_schema_metadata_and_contracts.py -v
   
   # Run all tests
   uv run pytest tests/ -v
   ```

2. **Type Checking**:
   ```bash
   uv run mypy src/strands_cli
   # Should pass with no errors
   ```

3. **Linting**:
   ```bash
   uv run ruff check .
   # Should pass with no violations
   ```

4. **Feature-Specific Tests**:
   
   a. **Atomic CLI**:
   ```bash
   # List atomic agents
   uv run strands atomic list
   
   # Describe agent
   uv run strands atomic describe summarize_customer_email
   
   # Initialize new agent
   uv run strands atomic init test_agent --domain testing --capability echo
   
   # Validate agent
   uv run strands atomic validate test_agent
   ```
   
   b. **Agent Composition**:
   ```bash
   # Validate composite workflow
   uv run strands validate examples/customer-support-intake-composite-openai.yaml
   
   # Plan composite workflow (shows resolved agents)
   uv run strands plan examples/customer-support-intake-composite-openai.yaml
   ```
   
   c. **Contract Validation**:
   ```bash
   # Run atomic agent with input validation (requires valid input.json)
   uv run strands atomic run summarize_customer_email \
     --input-file examples/data/sample_email.json \
     --output-file output.json
   ```
   
   d. **Testing Framework**:
   ```bash
   # Run agent tests
   uv run strands atomic test summarize_customer_email
   # Should show test results (pass/fail)
   ```

5. **End-to-End Workflow**:
   ```bash
   # Run composite workflow (requires OpenAI API key)
   export OPENAI_API_KEY=your-key-here
   uv run strands run examples/customer-support-intake-composite-openai.yaml \
     --var email_body="I need help with my account" \
     --var email_subject="Account Issue"
   ```

---

### Rollback Procedure

If integration fails:

1. **Discard all changes**:
   ```bash
   git checkout .
   git clean -fd
   ```

2. **Or restore from backup branch**:
   ```bash
   git checkout main
   git branch -D integrate-atomic-agents
   ```

3. **Or selective rollback** (remove specific files/directories):
   ```bash
   # Remove atomic directories
   Remove-Item agents/atomic -Recurse -Force
   Remove-Item src/strands_cli/atomic -Recurse -Force
   
   # Revert modified files
   git checkout HEAD -- CHANGELOG.md README.md src/strands_cli/__main__.py
   # ... (list all modified files)
   ```

---

## Code Changes Detail

### `src/strands_cli/__main__.py`

**Purpose**: CLI entry point with command routing

**Key Additions**:

##### `app.add_typer(atomic_app, name="atomic")` (New)

**Purpose**: Register atomic agents CLI subcommands

**Signature**:
```python
app.add_typer(atomic_app, name="atomic")
```

**Usage Example**:
```bash
strands atomic list
strands atomic describe <name>
strands atomic run <name> --input-file <path>
```

**Dependencies**: Imports `atomic_app` from `strands_cli.atomic.cli`

---

### `src/strands_cli/loader/yaml_loader.py`

**Purpose**: YAML/JSON workflow spec loading with validation

**Key Additions**:

##### `_resolve_agent_references(spec_data, spec_path)` (New)

**Purpose**: Resolve `$ref` in agent definitions to enable atomic agent composition

**Signature**:
```python
def _resolve_agent_references(spec_data: dict[str, Any], spec_path: Path) -> None
```

**What it does**:
- Parses `$ref` field in agent definitions (format: `path/to/file.yaml#/agents/agent_id`)
- Resolves file paths relative to composite workflow
- Loads referenced atomic agent spec
- Extracts agent definition via JSONPointer
- Resolves schema paths relative to atomic agent file (not composite)
- Merges with override fields (tools, model_id, provider, inference)
- Detects circular and nested references

**Usage Example**:
```yaml
agents:
  classifier:
    $ref: ./agents/atomic/classify_ticket_priority.yaml#/agents/classifier
    tools: ["http_request"]  # Override
```

**Migration Notes**: Called before schema validation in `load_spec` to resolve references before type checking

---

### `src/strands_cli/types.py`

**Purpose**: Pydantic v2 type definitions for all workflow specs

**Key Modifications**:

##### `Agent.ref` (New)

**Purpose**: Support agent references for composition

**Signature**:
```python
ref: str | None = Field(None, alias="$ref", description="Reference to external agent spec")
```

**What Changed**: Agent can now be defined by reference instead of inline prompt

**Before** (conceptual):
```python
# Only inline definition supported
class Agent(BaseModel):
    prompt: str
    tools: list[str] | None = None
```

**After** (from migration):
```python
# Support both inline and reference
class Agent(BaseModel):
    ref: str | None = Field(None, alias="$ref")  # NEW
    prompt: str | None = None  # Now optional
    tools: list[str] | None = None
    
    @model_validator(mode="after")
    def check_prompt_or_ref(self) -> "Agent":
        """Ensure either prompt or ref is present."""
        if not self.prompt and not self.ref:
            raise ValueError("Agent must have either 'prompt' or '$ref'")
        return self
```

**Migration Notes**: Uses Pydantic `alias="$ref"` to support `$` in YAML keys (not valid Python identifiers)

---

##### `Agent.input_schema` and `Agent.output_schema` (New)

**Purpose**: Contract schemas for atomic agents

**Signature**:
```python
input_schema: str | dict[str, Any] | None = None
output_schema: str | dict[str, Any] | None = None
```

**What Changed**: Agents can now declare input/output contracts

**Usage**:
```yaml
agents:
  classifier:
    prompt: "Classify input"
    input_schema: ./schemas/input.json  # Path to JSON Schema
    output_schema: ./schemas/output.json
```

---

##### `Metadata.labels` (New)

**Purpose**: Support atomic agent discovery metadata

**Signature**:
```python
labels: dict[str, str] | None = None
```

**What Changed**: Metadata can now include arbitrary labels for classification

**Usage**:
```yaml
metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/domain: customer_service
    strands.io/capability: summarization
```

---

### `src/strands_cli/atomic/cli.py`

**Purpose**: Typer CLI application for atomic agent commands

**Key Additions**:

All functions are new. Key commands:

##### `list_atomic()` (New)

**Purpose**: Discover atomic agents in repository

**Usage**:
```bash
strands atomic list
strands atomic list --all  # Include non-atomic agents
strands atomic list --json # JSON output
```

---

##### `describe_atomic(name)` (New)

**Purpose**: Show agent metadata, labels, and contracts

**Usage**:
```bash
strands atomic describe summarize_customer_email
strands atomic describe summarize_customer_email --format json
```

---

##### `run_atomic(name, input_file, output_file)` (New)

**Purpose**: Execute atomic agent with input/output schema validation

**Usage**:
```bash
strands atomic run summarize_customer_email \
  --input-file examples/data/email.json \
  --output-file result.json
```

**Validation**:
- Input validated against `input_schema`
- Output validated against `output_schema`
- Atomic invariants checked before execution

---

##### `test_atomic(name, filter_pattern)` (New)

**Purpose**: Run agent test suite from `tests.yaml`

**Usage**:
```bash
strands atomic test summarize_customer_email
strands atomic test summarize_customer_email --filter "long_email"
strands atomic test summarize_customer_email --json
```

---

##### `init_atomic(name, domain, capability, force)` (New)

**Purpose**: Scaffold new atomic agent with templates

**Usage**:
```bash
strands atomic init my_agent --domain testing --capability echo
```

**Generates**:
- `agents/atomic/my_agent/my_agent.yaml`
- `agents/atomic/my_agent/schemas/input.json`
- `agents/atomic/my_agent/schemas/output.json`
- `agents/atomic/my_agent/tests.yaml`
- `agents/atomic/my_agent/examples/sample.json`

---

##### `validate_atomic(path_or_name)` (New)

**Purpose**: Check atomic invariants and contract file existence

**Usage**:
```bash
strands atomic validate summarize_customer_email
```

**Checks**:
- Exactly one agent definition
- Single-step pattern (chain or workflow)
- No nested references
- Schema files exist on disk

---

### `src/strands_cli/atomic/core.py`

**Purpose**: Core logic for atomic agent discovery and validation

**Key Functions** (all new):

- `find_atomic_specs(root: Path) -> list[Path]` - Recursive discovery
- `resolve_atomic_spec(name: str, root: Path) -> Path | None` - Name resolution
- `check_atomic_invariants(spec: Spec) -> list[str]` - Validate atomic constraints

---

## File Contents

All complete file contents are located in `./files/` subdirectory, preserving the original directory structure from the source repository.

To view a file:
```bash
Get-Content "./files/<file_path>"
```

Example:
```bash
Get-Content "./files/src/strands_cli/atomic/cli.py"
Get-Content "./files/manual/explanation/atomic-agents.md"
```

---

## Notes

- This migration was auto-generated from uncommitted changes
- All changes are **additive** and **backward-compatible**
  - Existing workflows continue to work unchanged
  - `$ref` and atomic agent features are optional
  - No breaking changes to CLI or schema
- **Review all changes carefully** before applying to production
- Consider creating a PR in target repo for review
- Test thoroughly after integration (see Testing Strategy section)
- The atomic agents feature is designed for **composability and reuse**
  - Write atomic agents once, use in many workflows
  - Test agents in isolation before composition
  - Discover available agents with `strands atomic list`

---

## Support

If you encounter issues during migration:

1. **Check context files**:
   - `context/git-status.txt` for original file states
   - `context/branch-info.txt` for source context

2. **Compare files manually**:
   ```bash
   code --diff "./files/<file_path>" "<target_repo>/<file_path>"
   ```

3. **Run diagnostic commands**:
   ```bash
   # Check atomic CLI availability
   uv run strands atomic --help
   
   # Validate agent references
   uv run strands validate examples/customer-support-intake-composite-openai.yaml
   
   # Run atomic agent tests
   uv run pytest tests/test_agent_references.py -v
   ```

4. **Review error messages**: Atomic agents feature has comprehensive error handling with actionable messages
   - Agent reference resolution errors show exact file paths and JSONPointers
   - Circular reference detection shows reference chain
   - Schema validation errors include field paths and expected types

---

## Quick Migration Checklist

- [ ] Back up target repository
- [ ] Create integration branch: `git checkout -b integrate-atomic-agents`
- [ ] Copy all files from `./files/` to target repo (preserve directory structure)
- [ ] Review and manually merge modified files (15 files)
- [ ] Run tests: `uv run pytest tests/test_agent_references.py tests/test_atomic_cli.py -v`
- [ ] Run type check: `uv run mypy src/strands_cli`
- [ ] Run linting: `uv run ruff check .`
- [ ] Test atomic CLI: `uv run strands atomic list`
- [ ] Validate composite workflow: `uv run strands validate examples/customer-support-intake-composite-openai.yaml`
- [ ] Build documentation: `mkdocs build` (if using MkDocs)
- [ ] Commit changes: `git add . && git commit -m "feat: Add atomic agents support"`
- [ ] Create PR for review (recommended)
- [ ] Merge to main branch after approval

---

**End of Migration Guide**
