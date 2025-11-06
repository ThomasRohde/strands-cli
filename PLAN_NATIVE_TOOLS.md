# Plan: Native Tools Architecture (Simplified & Pragmatic)

**Date:** 2025-11-06  
**Status:** ✅ REVISED - Ready for Implementation  
**Version:** 2.0 (Major Simplification from v1.0)

---

## 🎯 Executive Summary (TL;DR)

**Goal:** Enable easy addition of native tools without modifying core code

**Solution:** Minimal registry pattern with auto-discovery (one file per tool)

**MVP Scope (Revised):**
- ✅ Build registry infrastructure for auto-discovery
- ✅ Keep existing `strands_tools.*` implementations as-is (no migration!)
- ✅ Implement ONE new native tool: `python_exec` (execute Python code safely)
- ✅ Prove the pattern works without disrupting existing functionality

**Impact:**
- 📁 Add tools by dropping `.py` files in `tools/` directory
- 🔒 100% backward compatible - zero changes to existing tools or examples
- ⚡ No schema changes, minimal runtime changes (~15 lines modified)
- 🚀 Implementation time: **2-3 days** (even faster than v2.0!)
- 📦 Code footprint: **~300 new lines** (registry + 1 tool + tests)

**Key Insight from Code Audit:**
> Current implementation already handles 80% of requirements! We just need:
> 1. Auto-discovery mechanism (registry) → 100 lines
> 2. Dynamic allowlist (replace hardcoded constant) → 5 lines
> 3. Backward-compat path resolution → 10 lines
> 4. ONE proof-of-concept tool (python_exec) → 100 lines

---

## Revision Summary (v2.0)

**Critical Changes Based on Code Review:**

1. ✅ **Schema Already Supports Free-Form Strings**: Current schema accepts any string in `tools.python[]` without strict patterns - **no schema changes needed**
2. ✅ **TOOL_SPEC Support Already Implemented**: `tools.py:load_python_callable()` already checks for `TOOL_SPEC` and returns modules directly (lines 76-80)
3. ⚠️ **Python Tool Config Uses Objects**: Schema uses `PythonTool` objects with `.callable` field, not bare strings
4. 📦 **Simplified Registry Pattern**: Minimal `ToolInfo` dataclass (not heavy `ToolSpec`); focus on discovery + allowlist
5. 🚀 **Performance Already Optimized**: Model clients use `@lru_cache` (providers.py), agents cached via `AgentCache` - no pooling changes needed
6. ❌ **Remove Over-Engineering**: No `ToolCategory` enum, complex metadata tracking, base classes, or subdirectories per tool in MVP

### What Changed from v1.0 → v2.0

| Aspect | v1.0 (Over-Engineered) | v2.0 (Pragmatic) |
|--------|----------------------|-----------------|
| **Structure** | Subdirs per tool/family | Flat: one file per tool |
| **ToolSpec** | Heavy dataclass with 10+ fields | Minimal `ToolInfo` (3 fields) |
| **Base Classes** | Abstract `NativeTool` class | None (follow Strands SDK) |
| **Schema Changes** | Add regex patterns | None needed ✅ |
| **Complexity** | ~15 new files, 2000+ LOC | ~7 new files, ~800 LOC |
| **Timeline** | 2-4 weeks | 6-9 days |

### Key Insight from Code Audit

**Current `tools.py` is already 80% there!** It:
- ✅ Detects `TOOL_SPEC` and returns modules
- ✅ Supports old/new format normalization
- ✅ Validates against allowlist

**We only need:**
- Auto-discovery mechanism (registry)
- Dynamic allowlist generation (replace hardcoded constant)
- Backward-compat path resolution

**Total code changes:** ~100 lines of new registry code + ~15 lines of modifications to existing files.

---

## Executive Summary

This plan describes a **simplified, pragmatic architecture** for incorporating native tools into the codebase. The design supports:

- **One tool per module file** with Strands SDK-compatible `TOOL_SPEC` exports (e.g., `tools/http_request.py`, `tools/calculator.py`)
- **Backward compatibility** with existing `strands_tools.*` format
- **Auto-discovery** via directory scanning (no manual registration)
- **Registry-based allowlist** replacing hardcoded `ALLOWED_PYTHON_CALLABLES`
- **Zero schema changes** (current schema already flexible enough)
- **Minimal runtime changes** (leverage existing `TOOL_SPEC` detection)

---

## 0. Official Documentation Verification ✓

**Source:** https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/python-tools/

### Alignment with Strands SDK Patterns

The proposed native tools architecture aligns with **three official tool patterns** supported by the Strands SDK:

#### 1. **@tool Decorator (Function-Decorated Tools)** ✓
The SDK supports `@tool` decorated functions for simple tools:
```python
from strands import tool

@tool
def weather_forecast(city: str, days: int = 3) -> str:
    """Get weather forecast for a city."""
    return f"Weather forecast for {city}..."
```

**Plan Alignment:** Our `NativeTool` base class and implementations can support both decorated and module-based approaches.

#### 2. **Class-Based Tools** ✓
The SDK supports class methods with `@tool` decorator for stateful tools:
```python
class DatabaseTools:
    @tool
    def query_database(self, sql: str) -> dict:
        """Run a SQL query."""
        return {"results": ...}
```

**Plan Alignment:** Our tool registry can instantiate and manage class-based tool instances.

#### 3. **Module-Based Tools (TOOL_SPEC)** ✓ **KEY PATTERN**
The SDK officially supports module-based tools with explicit `TOOL_SPEC` definition:
```python
# weather_forecast.py

TOOL_SPEC = {
    "name": "weather_forecast",
    "description": "Get weather forecast for a city.",
    "inputSchema": {...}
}

def weather_forecast(tool, **kwargs):
    tool_use_id = tool["toolUseId"]
    tool_input = tool["input"]
    return {
        "toolUseId": tool_use_id,
        "status": "success",
        "content": [{"text": result}]
    }
```

**Plan Alignment:** ✅ **This is exactly what our plan proposes!** The module-based approach with `TOOL_SPEC` is the foundation for:
- Tool discovery via module imports
- Explicit schema definition
- Self-contained tool definitions
- Registry auto-discovery

### Key Verification Points

| Plan Element | Official Pattern | Status |
|---|---|---|
| `TOOL_SPEC` export in each module | Strands SDK standard | ✅ **Verified** |
| Module-based tool loading | Supported by SDK | ✅ **Verified** |
| Tool response format (toolUseId, status, content) | SDK standard | ✅ **Verified** |
| Async tool support | Supported by SDK | ✅ **Verified** |
| Tool streaming (yield intermediate results) | Supported by SDK | ✅ **Verified** |
| ToolContext for invocation state | Supported by SDK | ✅ **Verified** |
| Multiple tools per module/class | Supported by SDK | ✅ **Verified** |

### Impact on Plan

The official documentation **validates and strengthens** the plan:

1. **Module-based approach is official:** Using `TOOL_SPEC` in each tool module is the recommended pattern for non-decorator-dependent tools
2. **Tool response format is standardized:** Our adapters can leverage the official format directly
3. **Async tools are first-class:** Plan's async support via `await execute()` aligns with SDK
4. **Self-contained modules:** Each tool in `tools/<family>/` can be self-contained and SDK-compatible
5. **No breaking changes:** Strands SDK supports flexible tool registration

### Recommendation

The plan's use of `TOOL_SPEC` and module-based discovery is **officially sanctioned** by Strands and represents **best practice** for tool organization. No plan modifications needed; this validates the architectural approach.

---

## 1. Current State Analysis

### 1.1 Current Tool Architecture

**Location:** `src/strands_cli/runtime/tools.py`

**Current Tool Types:**
- `PYTHON` tools: Hardcoded allowlist in `capability/checker.py`
  ```python
  ALLOWED_PYTHON_CALLABLES = {
      "strands_tools.http_request.http_request",
      "strands_tools.file_read.file_read",
      "strands_tools.file_write.file_write",
      "strands_tools.calculator.calculator",
      "strands_tools.current_time.current_time",
      # Also old format for backward compatibility:
      "strands_tools.http_request",
      "strands_tools.file_read",
      # ...
  }
  ```
- `HTTP_EXECUTORS`: Dynamic HTTP API configuration (works fine)
- `MCP`: Model Context Protocol (unsupported in MVP)

**Current Load Mechanism:**
1. Spec contains `tools.python` array with objects: `[{callable: "strands_tools.http_request"}]`
2. `_load_python_tools()` in `strands_adapter.py` iterates and calls `load_python_callable()`
3. `load_python_callable()` validates against `ALLOWED_PYTHON_CALLABLES`
4. If module has `TOOL_SPEC`, returns the module; otherwise returns the callable function
5. Tools are cached per agent in `AgentCache`

**Schema Definition (Current):**
```json
"tools": {
  "type": "object",
  "properties": {
    "python": {
      "type": "array",
      "description": "Fully qualified callables or module paths.",
      "items": {
        "type": "string"  // ✅ Already accepts any string - no pattern enforcement
      }
    }
  }
}
```

**CRITICAL FINDING**: Schema is already permissive! No schema changes needed.

### 1.2 What Already Works

✅ **TOOL_SPEC detection implemented** (`tools.py` lines 76-80)  
✅ **Schema accepts any string** (no regex pattern restriction)  
✅ **Model client pooling** (`providers.py` uses `@lru_cache`)  
✅ **Agent caching** (`AgentCache` in executors)  
✅ **HTTP executors fully functional**  

### 1.3 Pain Points Requiring Refactor

❌ **Hardcoded allowlist** - Adding tools requires editing `capability/checker.py`  
❌ **No tool organization** - All tools conceptually in `strands_tools.*` namespace  
❌ **Allowlist duplication** - Both old/new formats manually tracked  
❌ **No discovery mechanism** - Can't enumerate available tools for `strands list-tools`  
❌ **Tight coupling** - Allowlist is in `capability/` but tools conceptually belong elsewhere  

### 1.4 Key Insights from Code Review

1. **Python tools config uses objects**: `spec.tools.python` is `list[PythonTool]` where each has a `callable` field
2. **Loader already handles TOOL_SPEC**: No changes needed to `load_python_callable()` core logic
3. **Tool resolution is simple**: Just need to map user input → allowlisted import path
4. **Performance is good**: Existing caching sufficient; no pooling issues observed

---

## 2. Proposed Architecture (Simplified)

### 2.1 Directory Structure

```
src/strands_cli/
├── tools/                           # NEW: Native tools root
│   ├── __init__.py                  # Auto-discovery + registry singleton
│   ├── registry.py                  # NEW: Simple registry (allowlist + metadata)
│   │
│   ├── http_request.py              # One file per tool (Strands SDK pattern)
│   ├── file_read.py
│   ├── file_write.py
│   ├── calculator.py
│   ├── current_time.py
│   └── ... (future tools)
│
├── runtime/
│   ├── tools.py                     # UPDATED: Use registry for allowlist
│   ├── strands_adapter.py           # NO CHANGES (already generic)
│   └── ...
│
├── capability/
│   ├── checker.py                   # UPDATED: Get allowlist from registry
│   └── ...
│
├── schema/
│   └── strands-workflow.schema.json # NO CHANGES (already flexible)
```

**Key Simplifications from v1.0:**
- ❌ No subdirectories per tool family (flat structure)
- ❌ No `ToolCategory` enum (not needed for MVP)
- ❌ No `base.py` abstract classes (tools are self-contained modules)
- ❌ No complex `ToolSpec` with versioning/deprecation (defer to phase 2)
- ✅ One file = one tool (clean, simple, Strands SDK compatible)

### 2.2 Tool Registry Design (Minimal)

**File:** `src/strands_cli/tools/registry.py`

The registry serves as a **simple allowlist generator** and **metadata provider**:

```python
"""Minimal tool registry for native tools."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolInfo:
    """Minimal tool metadata for discovery."""
    
    id: str                           # e.g., "http_request"
    module_path: str                  # e.g., "strands_cli.tools.http_request"
    description: str                  # From TOOL_SPEC["description"]
    
    @property
    def import_path(self) -> str:
        """Full import path for loading."""
        return self.module_path
    
    @property
    def legacy_path(self) -> str:
        """Backward-compatible 'strands_tools.*' path."""
        return f"strands_tools.{self.id}.{self.id}"
    
    @property
    def legacy_short(self) -> str:
        """Old short format."""
        return f"strands_tools.{self.id}"


class ToolRegistry:
    """Simple singleton registry for native tools."""
    
    _instance: "ToolRegistry | None" = None
    _tools: dict[str, ToolInfo] = {}
    
    def __new__(cls) -> "ToolRegistry":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._discover_tools()
        return cls._instance
    
    def _discover_tools(self) -> None:
        """Auto-discover tools from strands_cli.tools module.
        
        Scans for Python files in tools/ directory, imports them,
        and checks for TOOL_SPEC export.
        """
        import importlib
        import pkgutil
        from pathlib import Path
        
        tools_dir = Path(__file__).parent
        
        # Scan all .py files (skip __init__, registry, etc.)
        for importer, module_name, is_pkg in pkgutil.iter_modules([str(tools_dir)]):
            if module_name.startswith("_") or module_name == "registry":
                continue
            
            try:
                module = importlib.import_module(f"strands_cli.tools.{module_name}")
                
                # Check for TOOL_SPEC (Strands SDK pattern)
                if hasattr(module, "TOOL_SPEC"):
                    spec = module.TOOL_SPEC
                    tool_info = ToolInfo(
                        id=spec["name"],
                        module_path=f"strands_cli.tools.{module_name}",
                        description=spec.get("description", ""),
                    )
                    self._tools[tool_info.id] = tool_info
            
            except Exception:
                # Silently skip malformed modules during discovery
                pass
    
    def get(self, tool_id: str) -> ToolInfo | None:
        """Get tool by ID."""
        return self._tools.get(tool_id)
    
    def list_all(self) -> list[ToolInfo]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def resolve(self, user_input: str) -> str | None:
        """Resolve user input to canonical import path.
        
        Supports:
        - "http_request" → "strands_cli.tools.http_request"
        - "strands_tools.http_request" → "strands_cli.tools.http_request"
        - "strands_tools.http_request.http_request" → "strands_cli.tools.http_request"
        
        Returns:
            Canonical import path or None if not found
        """
        # Direct ID lookup
        if user_input in self._tools:
            return self._tools[user_input].import_path
        
        # Legacy format: "strands_tools.X" or "strands_tools.X.X"
        if user_input.startswith("strands_tools."):
            parts = user_input.split(".")
            tool_id = parts[1] if len(parts) >= 2 else None
            if tool_id and tool_id in self._tools:
                return self._tools[tool_id].import_path
        
        return None
    
    def get_allowlist(self) -> set[str]:
        """Generate complete allowlist for capability checker.
        
        Returns all valid import formats for all tools.
        """
        allowlist = set()
        for tool in self._tools.values():
            allowlist.add(tool.import_path)       # New: "strands_cli.tools.http_request"
            allowlist.add(tool.legacy_path)       # Legacy: "strands_tools.http_request.http_request"
            allowlist.add(tool.legacy_short)      # Legacy: "strands_tools.http_request"
        return allowlist


def get_registry() -> ToolRegistry:
    """Get the global tool registry singleton."""
    return ToolRegistry()
```

**Key Features:**
- ✅ Auto-discovery on first import (singleton pattern)
- ✅ No manual registration needed
- ✅ Backward compat for `strands_tools.*` paths
- ✅ Generates allowlist dynamically
- ✅ Simple metadata extraction from `TOOL_SPEC`
- ❌ No versioning (defer to phase 2)
- ❌ No deprecation tracking (defer to phase 2)
- ❌ No complex validation (just presence check)

### 2.3 Tool Discovery & Registration

**File:** `src/strands_cli/tools/__init__.py`

Tools are auto-discovered on module import:

```python
"""Native tools registry and discovery."""

from strands_cli.tools.registry import get_registry

# Auto-discover happens on first get_registry() call (singleton pattern)
# No explicit initialization needed

__all__ = ["get_registry"]
```

**That's it!** No complex entry points, no manual registration.

### 2.4 Example Tool Implementation (Strands SDK-Compatible)

**File:** `src/strands_cli/tools/http_request.py`

```python
"""HTTP request tool (Strands SDK module-based pattern).

Official Pattern: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/python-tools/
"""

from typing import Any
import httpx

# 1. Tool Specification (Strands SDK standard)
TOOL_SPEC = {
    "name": "http_request",
    "description": "Execute HTTP requests with timeout and retry logic.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "default": "GET"
                },
                "headers": {"type": "object"},
                "json_data": {"type": "object"},
                "timeout_ms": {"type": "integer", "default": 30000}
            },
            "required": ["url"]
        }
    }
}

# 2. Tool Function (Strands SDK standard)
def http_request(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Execute an HTTP request.
    
    Args:
        tool: Tool invocation object with toolUseId and input
    
    Returns:
        ToolResult dict with status and content
    """
    try:
        tool_use_id = tool.get("toolUseId", "")
        tool_input = tool.get("input", {})
        
        url = tool_input.get("url")
        method = tool_input.get("method", "GET").upper()
        headers = tool_input.get("headers", {})
        json_data = tool_input.get("json_data")
        timeout_ms = tool_input.get("timeout_ms", 30000)
        
        # Validate
        if not url:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": "Missing required 'url' parameter"}]
            }
        
        # Execute
        timeout = timeout_ms / 1000
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data
            )
        
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{
                "json": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text,
                }
            }]
        }
    
    except Exception as e:
        return {
            "toolUseId": tool.get("toolUseId", ""),
            "status": "error",
            "content": [{"text": f"HTTP request failed: {str(e)}"}]
        }
```

**No extra exports needed!** The registry scans for `TOOL_SPEC` automatically.

### 2.5 Runtime Integration

**File:** `src/strands_cli/runtime/tools.py` (UPDATED)

Update `load_python_callable()` to use registry:

```python
def load_python_callable(import_path: str) -> Any:
    """Load a Python tool using registry.
    
    Supports:
    - 'native:http_request' → looks up via registry
    - 'strands_tools.http_request' → backward compat via registry
    - Full paths for direct imports
    """
    from strands_cli.tools import get_registry
    
    registry = get_registry()
    
    # Try registry lookup first (handles native: and strands_tools: prefixes)
    spec = registry.get_by_import_path(import_path)
    if spec:
        # Load the actual tool
        try:
            module = importlib.import_module(spec.module_path)
            return getattr(module, spec.callable_name)
        except Exception as e:
            raise ToolError(f"Failed to load tool '{import_path}': {e}") from e
    
    # Check allowlist for safety
    if import_path not in registry.get_allowlist():
        raise ToolError(
            f"Python callable '{import_path}' not in allowlist. "
            f"Allowed: {', '.join(sorted(registry.get_allowlist()))}"
        )
    
    # Fallback: Direct import (for fully-qualified paths)
    try:
        module_path, func_name = import_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except Exception as e:
        raise ToolError(f"Failed to load tool '{import_path}': {e}") from e
```

### 2.8 Capability Checker Integration

**File:** `src/strands_cli/capability/checker.py` (UPDATED)

Replace hardcoded allowlist with registry:

```python
def _check_tool_allowlist(spec: Spec) -> list[CapabilityIssue]:
    """Validate tools against registry allowlist."""
    from strands_cli.tools import get_registry
    
    registry = get_registry()
    issues = []
    
    if spec.tools and spec.tools.python:
        for tool_path in spec.tools.python:
            is_valid, error = registry.validate_tool_path(tool_path)
            if not is_valid:
                issues.append(
                    CapabilityIssue(
                        severity="error",
                        message=error,
                        remediation=f"Use a valid tool from the native registry"
                    )
                )
    
    return issues
```

---

## 3. Implementation Roadmap (Simplified)

### Phase 1: Foundation (2-3 days)

- [ ] Create `src/strands_cli/tools/` directory (flat structure)
- [ ] Implement minimal `registry.py` (just `ToolInfo` + `ToolRegistry`)
- [ ] Implement `__init__.py` (expose `get_registry()`)
- [ ] Write tests for registry auto-discovery (`tests/unit/test_tools_registry.py`)
- [ ] ~~Update schema JSON~~ **NO SCHEMA CHANGES NEEDED** ✅

**Deliverable:** Registry infrastructure ready; auto-discovery working

### Phase 2: Implement Python Exec Tool (1 day)

- [ ] Create `tools/python_exec.py` with TOOL_SPEC (MVP - simple implementation)
  - Execute Python code string in isolated environment
  - Return stdout/stderr/result
  - Basic security: timeout, restricted builtins
- [ ] Update `capability/checker.py`: Extend `ALLOWED_PYTHON_CALLABLES` to include new tool path
- [ ] Write unit tests for `python_exec` tool
- [ ] Test integration: Create example workflow using `python_exec`

**Deliverable:** One working native tool proving the pattern; existing tools untouched

### Phase 3: Registry Integration & Testing (1 day)

- [ ] Update `capability/checker.py`: Use registry for allowlist (keep existing tools in hardcoded list)
- [ ] Update `runtime/tools.py`: Add registry resolution for new tools only
- [ ] Add CLI command: `strands list-tools` (enumerate native tools from registry)
- [ ] Test auto-discovery with python_exec
- [ ] Verify all 287 existing tests still pass
- [ ] Create example workflow: `examples/python-exec-demo.yaml`

**Deliverable:** Registry working; python_exec available; zero regression

### Phase 4: Documentation (1 day)

- [ ] Create `docs/TOOL_DEVELOPMENT.md` (simple guide for adding tools)
- [ ] Update CONTRIBUTING.md (mention tools/ directory)
- [ ] Update `.github/copilot-instructions.md` (new tool architecture)
- [ ] Add inline comments to `registry.py` for clarity

**Deliverable:** Complete documentation

**Total Estimated Time:** 6-9 days (vs 2 weeks in v1.0)

---

## 4. Key Design Principles (Updated for v2.0)

### 4.1 Backward Compatibility

**Requirement:** All existing `strands_tools.*` imports continue to work

**Implementation:**
- Registry's `resolve()` method translates legacy paths to new paths
- `get_allowlist()` includes both old and new formats
- No breaking changes to workflow specs
- Examples using old format continue to work

**Testing:** Run all 28 existing examples; all must pass

### 4.2 Minimal Changes Principle

**Requirement:** Leverage existing infrastructure; avoid over-engineering

**Implementation:**
- ✅ Schema already flexible - no changes needed
- ✅ `TOOL_SPEC` detection already implemented - reuse it
- ✅ Agent caching already works - no pooling changes
- ✅ Model client pooling already exists - no changes
- ➕ Only add: Registry for discovery + allowlist generation

### 4.3 Scalability via Auto-Discovery

**Requirement:** Adding a new tool = creating a single .py file

**Implementation:**
- Drop tool file (e.g., `tools/new_tool.py`) with `TOOL_SPEC`
- Registry auto-discovers on next import
- Immediately available in allowlist
- No code changes in `checker.py`, `tools.py`, or executors

**Example:**
```python
# tools/web_scraper.py
TOOL_SPEC = {
    "name": "web_scraper",
    "description": "Scrape web pages",
    "inputSchema": {...}
}

def web_scraper(tool, **kwargs):
    # Implementation
    return {"toolUseId": ..., "status": "success", ...}
```

That's it! Tool is now available.

### 4.4 Single Responsibility Per Module

| Module | Responsibility | Lines of Code (est.) |
|--------|---|---|
| `tools/registry.py` | Discovery, resolution, allowlist | ~100 |
| `tools/<tool>.py` | Tool implementation (one per file) | ~50-150 each |
| `runtime/tools.py` | Tool loading (add ~10 lines) | ~140 → 150 |
| `capability/checker.py` | Validation (modify ~5 lines) | ~450 → 455 |

**Total new code:** ~200 lines (registry) + 5 tool files × ~100 lines = ~700 lines
**Modified code:** ~15 lines across 2 files

### 4.5 No Premature Abstraction

**Deferred to Phase 2 (post-MVP):**
- ❌ `ToolCategory` enum (not needed yet)
- ❌ Base classes / abstract interfaces (tools are simple functions)
- ❌ Versioning / deprecation tracking (no use case yet)
- ❌ Complex metadata (description from TOOL_SPEC is sufficient)
- ❌ Tool-specific configuration beyond TOOL_SPEC

---

## 5. Critical Fixes & Changes from v1.0

### 5.1 ❌ Remove: Schema Changes

**v1.0 Proposed:** Add regex pattern to enforce `native:` prefix in schema

**v2.0 Reality:** Schema already accepts any string! No changes needed.

```json
// Current schema (sufficient!)
"items": { "type": "string" }
```

### 5.2 ❌ Remove: Complex ToolSpec Dataclass

**v1.0 Proposed:** Heavy `ToolSpec` with category, version, deprecation, timeout, consent, input/output schemas

**v2.0 Reality:** Simple `ToolInfo` with just `id`, `module_path`, `description`

**Rationale:** YAGNI - Add complexity when needed, not speculatively

### 5.3 ❌ Remove: Base Classes and Abstractions

**v1.0 Proposed:** `NativeTool` abstract base class in `base.py`

**v2.0 Reality:** Tools are Strands SDK-compatible modules with `TOOL_SPEC` - no inheritance needed

**Rationale:** Follow Strands SDK patterns; don't invent new ones

### 5.4 ❌ Remove: Subdirectories Per Tool

**v1.0 Proposed:** `tools/http_request/tool.py`, `tools/file_operations/file_read.py`

**v2.0 Reality:** Flat structure - `tools/http_request.py`, `tools/file_read.py`

**Rationale:** Simpler discovery; each tool is self-contained; no need for `__init__.py` exports

### 5.5 ✅ Keep: Auto-Discovery Pattern

**Both versions:** Use `pkgutil.iter_modules()` to scan for tools

**v2.0 Enhancement:** Scan for `.py` files (not subdirectories), check for `TOOL_SPEC` attribute

### 5.6 ✅ Keep: Backward Compatibility

**Both versions:** Support `strands_tools.*` legacy format

**v2.0 Implementation:** Via `resolve()` method in registry

### 5.7 ⚠️ Caution: Don't Break Existing Tools.py Logic

**Current `tools.py` already handles:**
- Old format: `strands_tools.http_request` (infers function name)
- New format: `strands_tools.http_request.http_request` (explicit)
- Module-based tools: Returns module if `TOOL_SPEC` present

**v2.0 Change:** Add registry resolution BEFORE existing logic (graceful enhancement)

---

## 6. Example Workflows (Backward Compatible)

**Old format (all 28 examples use this - must keep working!):**
```yaml
tools:
  python:
    - callable: strands_tools.http_request
    - callable: strands_tools.file_read.file_read
```

**Registry handles both via `resolve()`:**
- `strands_tools.http_request` → `strands_cli.tools.http_request`
- `strands_tools.file_read.file_read` → `strands_cli.tools.file_read`

**No breaking changes to existing workflows!**

---

## 7. Simplified Implementation Steps

### Step 1: Create Registry (90 minutes)

1. Create `src/strands_cli/tools/registry.py` (copy code from section 2.2)
2. Create `src/strands_cli/tools/__init__.py`:
   ```python
   from strands_cli.tools.registry import get_registry
   __all__ = ["get_registry"]
   ```
3. Write `tests/unit/test_tools_registry.py`:
   - Test auto-discovery
   - Test `resolve()` method
   - Test `get_allowlist()` output

### Step 2: Create Python Exec Tool (1 hour)

Create ONE new native tool to prove the pattern:

```python
# tools/python_exec.py
TOOL_SPEC = {
    "name": "python_exec",
    "description": "Execute Python code and return results (MVP - simple version)",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "default": 5, "description": "Timeout in seconds"}
            },
            "required": ["code"]
        }
    }
}

def python_exec(tool, **kwargs):
    """Execute Python code with timeout.
    
    MVP Implementation:
    - Uses exec() with restricted globals
    - Captures stdout via StringIO
    - Basic timeout via signal (Unix) or threading (Windows)
    - Returns result or error
    """
    import io
    import sys
    from contextlib import redirect_stdout
    
    tool_use_id = tool.get("toolUseId", "")
    tool_input = tool.get("input", {})
    code = tool_input.get("code", "")
    
    try:
        # Capture stdout
        output = io.StringIO()
        with redirect_stdout(output):
            # Restricted globals (no file I/O, imports, etc.)
            restricted_globals = {
                "__builtins__": {
                    "print": print,
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "list": list,
                    "dict": dict,
                    # Add more safe builtins as needed
                }
            }
            exec(code, restricted_globals)
        
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": output.getvalue() or "Code executed successfully"}]
        }
    
    except Exception as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Execution failed: {str(e)}"}]
        }
```

**Note:** This is MVP - a production version would add:
- Proper sandboxing (subprocess, docker, etc.)
- Resource limits (memory, CPU)
- Better timeout handling
- Allowlist of safe modules
- AST parsing for dangerous operations

### Step 3: Update Capability Checker (15 minutes)

In `capability/checker.py` - **hybrid approach** (keep existing + add registry):

```python
# KEEP existing hardcoded allowlist for strands_tools.*
ALLOWED_PYTHON_CALLABLES = {
    "strands_tools.http_request.http_request",
    "strands_tools.file_read.file_read",
    "strands_tools.file_write.file_write",
    "strands_tools.calculator.calculator",
    "strands_tools.current_time.current_time",
    # Old format
    "strands_tools.http_request",
    "strands_tools.file_read",
    "strands_tools.file_write",
    "strands_tools.calculator",
    "strands_tools.current_time",
}

def _validate_tools(spec: Spec, issues: list[CapabilityIssue]) -> None:
    from strands_cli.tools import get_registry
    
    registry = get_registry()
    # Combine existing allowlist + registry allowlist
    allowed = ALLOWED_PYTHON_CALLABLES | registry.get_allowlist()
    
    if spec.tools and spec.tools.python:
        for i, tool in enumerate(spec.tools.python):
            if tool.callable not in allowed:
                available = ', '.join(sorted(t.id for t in registry.list_all()))
                issues.append(
                    CapabilityIssue(
                        pointer=f"/tools/python/{i}/callable",
                        reason=f"Tool '{tool.callable}' not in allowlist",
                        remediation=f"Use existing tools or native tools: {available}",
                    )
                )
```

**Key:** Hybrid approach! Existing tools stay in hardcoded list; new native tools come from registry.

### Step 4: Update Runtime Tools (15 minutes)

In `runtime/tools.py`, update `load_python_callable()`:

```python
def load_python_callable(import_path: str) -> Any:
    from strands_cli.tools import get_registry
    
    registry = get_registry()
    
    # New: Check allowlist from registry
    if import_path not in registry.get_allowlist():
        raise ToolError(...)
    
    # New: Try to resolve via registry
    resolved_path = registry.resolve(import_path)
    if resolved_path:
        import_path = resolved_path
    
    # Rest of function UNCHANGED (existing TOOL_SPEC logic)
    ...
```

### Step 5: Test Everything (1 hour)

```powershell
.\scripts\dev.ps1 test          # All 287 tests must pass
.\scripts\dev.ps1 validate-examples  # All 28 examples must validate

# Test specific patterns
uv run strands run examples/chain-calculator-openai.yaml --var operation="2+2"
uv run strands run examples/simple-file-read-openai.yaml
```

### Step 6: Add CLI Command (30 minutes)

In `__main__.py`:

```python
@app.command()
def list_tools() -> None:
    """List all available native tools."""
    from strands_cli.tools import get_registry
    
    registry = get_registry()
    tools = registry.list_all()
    
    console.print("[bold]Available Tools:[/bold]\n")
    for tool in sorted(tools, key=lambda t: t.id):
        console.print(f"  • [cyan]{tool.id}[/cyan] - {tool.description}")
```

**Total Implementation Time: ~3-4 hours** (even faster - no migration!)

```python
"""ML tools module."""

from strands_cli.tools.ml_tools.embeddings import embeddings, EMBEDDINGS_SPEC
from strands_cli.tools.ml_tools.classifier import classifier, CLASSIFIER_SPEC

TOOL_SPECS = [EMBEDDINGS_SPEC, CLASSIFIER_SPEC]

__all__ = ["embeddings", "classifier", "TOOL_SPECS"]
```

**Usage:**
```yaml
tools:
  python:
    - native:embeddings
    - native:classifier
```

No changes to core code needed! Registry auto-discovers on import.

### 6.2 Adding a Custom Tool (Not in Native Registry)

If users want custom tools, they can:

1. Create a local module with tool implementation
2. Add to allowlist via environment variable or config
3. Reference in spec using full module path

**Capability checker updated to support custom tool configuration:**
```python
# In config.py or via env var
STRANDS_CUSTOM_TOOL_ALLOWLIST = [
    "mycompany.ml_tools.embedding_service",
    "mycompany.data_tools.query_warehouse",
]
```

---

## 7. Migration Path (Existing Code)

### 7.1 What Changes

| Component | Change | Effort |
|-----------|--------|--------|
| `capability/checker.py` | Use registry instead of hardcoded set | Low |
| `runtime/tools.py` | Use registry lookup | Low |
| `strands_adapter.py` | No major changes (already generic) | None |
| `schema/strands-workflow.schema.json` | Add `native:` examples, update pattern | Low |
| Tool files | Move to new location, add TOOL_SPECS | Medium |

### 7.2 What Stays the Same

- ✅ `types.py` (Tool, ToolType enums unchanged)
- ✅ Pattern execution (chain, workflow, routing, parallel)
- ✅ Agent invocation and caching
- ✅ Artifact output
- ✅ Most CLI commands

### 7.3 Backward Compatibility Testing

```bash
# Old format (must work)
uv run strands run examples/chain-with-tools.yaml
  # with: tools.python: ["strands_tools.http_request", "strands_tools.file_read"]

# New format (must work)
uv run strands run examples/chain-with-native-tools.yaml
  # with: tools.python: ["native:http_request", "native:file_read"]

# Mixed format (must work)
uv run strands run examples/chain-mixed-tools.yaml
  # with: tools.python: ["native:http_request", "strands_tools.file_read"]
```

All three must pass existing test suite (~287 tests).

---

## 8. Future Extensions

### 8.1 Tool Configuration Schema

Each tool family can define input/output schemas:

```python
# tools/http_request/schema.py

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "format": "uri"},
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
        "json_data": {"type": "object"},
    },
    "required": ["url", "method"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "integer"},
        "headers": {"type": "object"},
        "body": {"type": "string"},
    },
}
```

Registry can use these for:
- Validation in capability checker
- Auto-generation of CLI tool help
- Tracing and observability

### 8.2 Tool Versioning

Support multiple versions of same tool:

```python
TOOL_SPECS = [
    ToolSpec(id="http_request", version="1.0.0", ...),
    ToolSpec(id="http_request", version="2.0.0", ..., deprecated=False),
]

# Usage:
tools:
  python:
    - native:http_request@2.0.0  # Specific version
```

### 8.3 Conditional Tool Loading

Tools can have prerequisites:

```python
@dataclass
class ToolSpec:
    requires: dict[str, str] | None = None  # e.g., {"bedrock": ">=1.0"}
```

Registry validates all prerequisites before allowing tool use.

### 8.4 Tool Telemetry

Each tool auto-contributes to observability:

```python
# tools/registry.py
async def execute_tool_with_telemetry(tool_id: str, inputs: dict) -> Any:
    """Execute tool and emit OTEL span."""
    with tracer.start_as_current_span(f"tool:{tool_id}") as span:
        span.set_attribute("tool.id", tool_id)
        span.set_attribute("tool.inputs", str(inputs))
        result = await tool.execute(**inputs)
        span.set_attribute("tool.output_size", len(str(result)))
        return result
```

---

## 9. Risks & Mitigation (v2.0 Updated)

| Risk | v1.0 Assessment | v2.0 Reality | Mitigation |
|------|----------------|-------------|-----------|
| Breaking backward compat | Low / High | **Very Low / High** | All 28 examples must pass; `resolve()` handles legacy paths |
| Registry discovery failures | Medium / Medium | **Low / Low** | Simple scan logic; graceful skip on malformed modules |
| Performance regression | Low / Medium | **Very Low / Low** | No new caching needed; registry singleton cached |
| Schema validation too strict | Low / Medium | **N/A** | No schema changes! ✅ |
| Import order dependencies | **New** | **Low / Medium** | Registry lazy-loads on first access; singleton pattern prevents double-init |

**New Risk in v2.0:**
- **Tool name conflicts**: What if two tools have same `TOOL_SPEC["name"]`?
  - **Mitigation**: Last-wins during discovery + warning log; future: enforce uniqueness

---

## 10. Success Criteria (v2.0 - Revised)

**Must-Have (MVP):**
- [ ] Registry implemented with ≥85% test coverage
- [ ] ONE new native tool (`python_exec`) working end-to-end
- [ ] All 287 unit tests pass without modification
- [ ] All 28 example workflows run successfully (100% backward compat!)
- [ ] `strands list-tools` CLI command works (shows native tools)
- [ ] Example workflow using `python_exec` tool
- [ ] No performance regression
- [ ] Documentation updated (TOOL_DEVELOPMENT.md with python_exec example)

**Deferred (Phase 2 - Future Migration):**
- [ ] Migrate existing 5 tools from strands_tools.* to native format
- [ ] Remove hardcoded ALLOWED_PYTHON_CALLABLES
- [ ] Full registry-based validation

**Nice-to-Have (Future Phases):**
- [ ] Better python_exec: sandboxing, resource limits, safe imports
- [ ] Tool versioning support
- [ ] Deprecation warnings
- [ ] Tool input validation via JSON schema
- [ ] OTEL spans per tool invocation

---

## 11. Appendix: Directory Tree (Final State - v2.0 Revised)

```
src/strands_cli/
├── tools/                           # NEW
│   ├── __init__.py                  # Expose get_registry()
│   ├── registry.py                  # ~100 lines (ToolInfo + ToolRegistry)
│   └── python_exec.py               # ~100 lines (TOOL_SPEC + function) - ONLY NEW TOOL
│
├── runtime/
│   ├── tools.py                     # MODIFIED: +10 lines (registry integration)
│   ├── strands_adapter.py           # NO CHANGES
│   ├── providers.py                 # NO CHANGES
│   └── __init__.py
│
├── capability/
│   ├── checker.py                   # MODIFIED: -10 lines (remove constant), +5 lines (use registry)
│   ├── reporter.py                  # NO CHANGES
│   └── __init__.py
│
├── schema/
│   └── strands-workflow.schema.json # NO CHANGES ✅
│
└── ... (other modules unchanged)

tests/
├── unit/
│   └── test_tools_registry.py       # NEW: ~100 lines (discovery, resolve, allowlist)
└── integration/
    └── test_backward_compat.py      # NEW: ~80 lines (old format still works)
```

**Code Stats:**
- **New code**: ~300 lines (registry + 1 tool + tests)
- **Modified code**: ~10 lines (2 files - hybrid approach)
- **Removed code**: 0 lines (keeping existing tools as-is!)
- **Net addition**: ~310 lines
- **Files touched**: 6 (vs 30+ in v1.0, vs 9 in v2.0-migration)
- **Risk**: Minimal (new code path only; existing tools untouched)

---

## 12. Timeline Estimate (v2.0 - Revised with python_exec)
│   └── test_tools_integration.py      # NEW: Integration tests
└── fixtures/
    └── tools/
        ├── native_tools_spec.yaml     # NEW: Example with native: prefix
        └── legacy_tools_spec.yaml     # Legacy format examples
```

---

## 12. Timeline Estimate (v2.0 Realistic)

| Phase | Duration | Effort | Dependencies |
|-------|----------|--------|--------------|
| Phase 1: Registry Foundation | 0.5 days | Registry code + discovery | None |
| Phase 2: Tool Migration | 1 day | Create 5 tool files | Phase 1 ✓ |
| Phase 3: Integration | 0.5 days | Update checker + tools.py | Phase 2 ✓ |
| Phase 4: Testing | 1 day | Unit + integration tests | Phase 3 ✓ |
| Phase 5: CLI & Docs | 1 day | list-tools cmd + docs | Phase 4 ✓ |
| **Total** | **~4 days** | **1 developer** | - |

**vs v1.0 Estimate:** 2-4 weeks → **5-10x faster!**

**Breakdown by Activity:**
- Writing code: 2 days
- Testing: 1 day
- Documentation: 1 day
- Contingency: Included in estimates

---

## 13. Decision Log

| # | Question | v1.0 Decision | v2.0 Decision | Rationale |
|---|----------|--------------|--------------|-----------|
| 1 | Auto-discovery vs manual registration? | Auto-discovery | ✅ **Same** | Simpler DX |
| 2 | Singleton vs instance registry? | Singleton | ✅ **Same** | Global truth |
| 3 | Subdirectories vs flat structure? | Subdirectories | ❌ **Flat** | Simpler; fewer files |
| 4 | Schema changes needed? | Yes (regex) | ❌ **No** | Already flexible |
| 5 | Base classes for tools? | Yes (NativeTool) | ❌ **No** | Follow Strands SDK |
| 6 | Tool versioning in MVP? | Deferred | ✅ **Same** | YAGNI |
| 7 | ToolSpec complexity? | 10+ fields | ❌ **3 fields** | Minimal viable |
| 8 | Support native: prefix? | Yes | ⚠️ **Later** | Not needed for discovery |

---

## 14. Critique of v1.0 Plan

### What v1.0 Got Right ✅

1. **Auto-discovery pattern** - Correct approach for scalability
2. **Backward compatibility** - Critical for production systems
3. **Strands SDK alignment** - Using TOOL_SPEC is official pattern
4. **Single source of truth** - Registry is the right abstraction
5. **Documentation emphasis** - Developer experience matters

### What v1.0 Over-Engineered ❌

1. **Subdirectories per tool** - Unnecessary complexity for 5-10 tools
2. **Heavy ToolSpec dataclass** - 10+ fields when only 3 needed
3. **ToolCategory enum** - No use case in MVP
4. **Base classes** - Strands SDK doesn't require them
5. **Schema regex patterns** - Current schema already permissive
6. **Model client pooling** - Already implemented via @lru_cache!
7. **Agent caching strategy** - Already implemented via AgentCache!

### What v1.0 Missed 🔍

1. **Code already 80% there** - Didn't audit existing `tools.py` implementation
2. **TOOL_SPEC detection exists** - Lines 76-80 already handle module-based tools
3. **PythonTool uses .callable** - v1.0 assumed bare strings in schema
4. **Performance already optimized** - Assumed caching needed implementation

### Lessons Learned 📚

1. **Audit before architecting** - Review existing code first
2. **YAGNI principle** - Don't add features without concrete use cases
3. **Leverage SDK patterns** - Follow official docs, don't invent abstractions
4. **Minimal viable changes** - Smallest change that solves the problem
5. **Test-driven estimates** - Count existing tests as constraints

---

**End of Plan (v2.0)**

---

## 13. Decision Points

1. **Auto-discovery vs. Manual registration?**
   - **Decision:** Auto-discovery (via directory scan)
   - **Rationale:** Simpler developer experience; no boilerplate

2. **Singleton vs. Instance registry?**
   - **Decision:** Singleton
   - **Rationale:** Single source of truth; simpler CLI/runtime usage

3. **Registry in separate file or in `__init__.py`?**
   - **Decision:** Separate `registry.py`
   - **Rationale:** Cleaner; easier to test; import cycles prevented

4. **Support for tool versioning in MVP?**
   - **Decision:** Defer to Phase 2
   - **Rationale:** MVP focus on core refactor; versioning adds complexity

5. **Custom tool allowlist mechanism?**
   - **Decision:** Environment variable + future config file
   - **Rationale:** Supports users adding tools without core changes

---

**End of Plan**

---

## Appendix A: Strands SDK Integration Details

### Tool Module Format (Official Pattern)

Each tool module should follow the **official Strands SDK pattern**:

```python
# 1. Export TOOL_SPEC
TOOL_SPEC = {
    "name": "tool_name",
    "description": "...",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
}

# 2. Implement matching function
def tool_name(tool, **kwargs):
    """Match TOOL_SPEC name exactly."""
    tool_use_id = tool["toolUseId"]
    tool_input = tool["input"]
    
    # ... implementation ...
    
    return {
        "toolUseId": tool_use_id,
        "status": "success" | "error",
        "content": [{"text": "..."} | {"json": {...}}]
    }
```

This allows tools to be:
- ✅ Used directly with Strands Agent
- ✅ Used via strands-cli with registry discovery
- ✅ Packaged for community/marketplace
- ✅ Version-controlled without dependencies

### ToolResult Format (Strands SDK Standard)

All tools must return the standard format:

```python
{
    "toolUseId": str,           # Echo back from input
    "status": "success|error",  # Execution result
    "content": [
        {"text": "..."},        # Plain text
        {"json": {...}},        # JSON data
        {"image": {...}},       # Images (future)
        {"document": {...}}     # Documents (future)
    ]
}
```

### Tool Streaming (Strands SDK Feature)

Async tools can yield intermediate results:

```python
async def streaming_tool(tool, **kwargs):
    """Tool with progress updates."""
    for i in range(10):
        # Yield intermediate result (not yet part of strands-cli)
        yield f"Processing {i}/10..."
    
    return {
        "toolUseId": tool["toolUseId"],
        "status": "success",
        "content": [{"text": "Done"}]
    }
```

strands-cli will support streaming in Phase 4.

---

**End of Plan**
