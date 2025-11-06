# Security Considerations

## Overview

Strands CLI executes user-defined workflow specifications that may include templates, HTTP executors, and file operations. This document describes the security measures implemented to protect against common attack vectors when processing potentially untrusted workflow specs.

**Security Principle**: Defense-in-depth for user-editable specifications. All user-controlled inputs (YAML specs, templates, variables) are treated as potentially malicious and validated at multiple layers.

---

## Template Security (Jinja2 Sandboxing)

### Risk: Remote Code Execution via Template Injection

Workflow specs use Jinja2 templates for dynamic content rendering in prompts, inputs, and artifact paths. Without proper sandboxing, attackers can exploit template introspection to execute arbitrary Python code.

**Attack Example**:
```yaml
outputs:
  artifacts:
    - path: "output.txt"
      from: "{{ ''.__class__.__mro__[1].__subclasses__()[104].__init__.__globals__['os'].system('malicious_command') }}"
```

### Mitigation: Sandboxed Environment

**Implementation** (`src/strands_cli/loader/template.py`):
- Uses `jinja2.sandbox.SandboxedEnvironment` instead of standard `Environment`
- Explicitly whitelists only safe filters: `truncate`, `tojson`
- Clears all globals to prevent access to Python builtins
- Blocks attribute access to `__class__`, `__mro__`, `__subclasses__`, `__globals__`, etc.

**Detection & Logging**:
```python
# Security violations logged at WARNING level
logger.warning(
    "template_security_violation",
    violation_type="unsafe_operation",
    error=str(e),
    template_preview=template_str[:100],
)
```

**What's Allowed**:
- Variable expansion: `{{ variable }}`
- Whitelisted filters: `{{ text | truncate(100) }}`, `{{ data | tojson }}`
- Safe attribute access: `{{ inputs.topic }}`
- Whitelisted filters: `{{ text | truncate(100) }}`, `{{ data | tojson }}`, `{{ topic | title }}`

**What's Blocked**:
- Python introspection: `{{ ''.__class__ }}`
- Builtin functions: `{{ eval(...) }}`, `{{ __import__(...) }}`
- Non-whitelisted filters: `{{ text | upper }}` (only `truncate`, `tojson`, and `title` are allowed)

---

## HTTP Executor Security (SSRF Prevention)

### Risk: Server-Side Request Forgery (SSRF)

HTTP executors allow specs to define arbitrary `base_url` values. Without validation, attackers can target internal services, cloud metadata endpoints, or local files.

**Attack Example**:
```yaml
tools:
  http_executors:
    - id: "metadata-attack"
      base_url: "http://169.254.169.254/latest/meta-data/"  # AWS metadata
      timeout: 30
```

### Mitigation: URL Validation with Blocklist/Allowlist

**Implementation** (`src/strands_cli/types.py`, `src/strands_cli/config.py`):

#### Default Blocked Patterns
Enforced for all HTTP executors:
- Localhost: `127.0.0.1`, `localhost`, `[::1]`
- AWS/Azure metadata: `169.254.169.254`
- Private networks (RFC1918): `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Non-HTTP protocols: `file://`, `ftp://`, `gopher://`

#### Environment Variable Configuration

**Add custom blocked patterns**:
```bash
export STRANDS_HTTP_BLOCKED_PATTERNS='["^https://internal-api\\.company\\.com"]'
```

**Enforce allowlist** (blocks all URLs except those matching patterns):
```bash
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\\.openai\\.com", "^https://.*\\.trusted\\.com"]'
```

**Detection & Logging**:
```python
# SSRF attempts logged at WARNING level
logger.warning(
    "http_url_blocked",
    violation_type="ssrf_attempt",
    blocked_url=base_url,
    matched_pattern=pattern,
)
```

**What's Allowed by Default**:
- Public HTTPS URLs: `https://api.openai.com`, `https://api.example.com`
- Public HTTP URLs: `http://api.example.com` (blocklist-based, not allowlist)

**What's Blocked**:
- Localhost/loopback addresses
- Private IP ranges
- Cloud metadata endpoints
- File/FTP/Gopher protocols
- Any URL matching `STRANDS_HTTP_BLOCKED_PATTERNS`
- If `STRANDS_HTTP_ALLOWED_DOMAINS` set: URLs not matching allowlist

---

## Artifact Path Security (Path Traversal Prevention)

### Risk: Path Traversal and File Overwrite

Artifact paths can include templates that render user variables. Without validation, attackers can escape the output directory, overwrite system files, or follow symlinks outside the project.

**Attack Examples**:
```yaml
outputs:
  artifacts:
    - path: "{{ malicious }}"
      from: "{{ last_response }}"
```
```bash
strands run workflow.yaml --var malicious="../../etc/passwd"
```

### Mitigation: Multi-Layer Path Validation

**Implementation** (`src/strands_cli/artifacts/io.py`):

#### 1. Reject Absolute Paths
```python
if path_obj.is_absolute():
    raise ArtifactError("Absolute paths not allowed in artifacts")
```

#### 2. Block Path Traversal (`..` components)
```python
if ".." in path_obj.parts:
    raise ArtifactError("Path traversal not allowed")
```

#### 3. Sanitize Path Components
Each component sanitized with `sanitize_filename()`:
- Removes path separators (`/`, `\`)
- Replaces special characters with `_`
- Strips leading/trailing dots and underscores

#### 4. Validate Resolved Path
```python
artifact_path.relative_to(output_dir.resolve())  # Raises ValueError if escaped
```

#### 5. Block Symlinks (MVP)
```python
if artifact_path.is_symlink():
    raise ArtifactError("Symlinks are not allowed for security reasons")
```

**Detection & Logging**:
```python
# Path traversal attempts logged at WARNING level
logger.warning(
    "artifact_path_blocked",
    violation_type="path_traversal_attempt",
    attempted_path=rendered_path,
    artifact_template=artifact.path,
)
```

**What's Allowed**:
- Relative paths: `output.txt`, `reports/summary.md`
- Nested directories: `analysis/data/results.json`
- Template variables: `{{ spec.name }}-report.txt`

**What's Blocked**:
- Absolute paths: `/etc/passwd`, `C:\Windows\System32\config`
- Path traversal: `../../etc/passwd`, `..\..\..\windows\hosts`
- Symlinks (for MVP; may be reconsidered in future releases)

---

## Python Tool Security

### Risk: Dangerous File Operations and Code Execution

Python tools can perform file operations and execute code within the workflow environment. The `file_write` tool, in particular, can modify the filesystem and requires careful usage.

**Attack Example**:
```yaml
tools:
  python:
    - callable: "strands_tools.file_write.file_write"
```
```bash
# Malicious prompt could attempt to overwrite system files
strands run workflow.yaml --var path="/etc/passwd" --var content="malicious"
```

### Mitigation: Allowlist + User Consent

**Implementation** (`src/strands_cli/capability/checker.py`, `src/strands_cli/runtime/tools.py`):

#### Allowlisted Python Tools
Only the following Python callables are permitted:
- `strands_tools.http_request.http_request` - Make HTTP requests (subject to SSRF protection)
- `strands_tools.file_read.file_read` - Read files (read-only access)
- `strands_tools.file_write.file_write` - Write files (requires consent)
- `strands_tools.calculator.calculator` - Mathematical calculations (SymPy-based)
- `strands_tools.current_time.current_time` - Get current date/time (read-only)

Any tool not in this allowlist will trigger exit code 18 with remediation report.

#### User Consent for file_write

The `file_write` tool includes **interactive consent prompts** to prevent unintended file modifications. The tool will:
1. Display the target file path and content preview
2. Prompt user to confirm the write operation
3. Allow user to deny (skip) or approve each write

**Bypassing Consent (Automation Mode)**:

For CI/CD pipelines and automation scenarios, use the `--bypass-tool-consent` flag:

```bash
strands run workflow.yaml --bypass-tool-consent
```

This sets the `BYPASS_TOOL_CONSENT=true` environment variable, which the Strands SDK's `file_write` tool respects.

**⚠️ Security Warning**: Only use `--bypass-tool-consent` in trusted, controlled environments:
- ✅ CI/CD pipelines with reviewed workflow specs
- ✅ Automated testing with known, safe inputs
- ❌ Production workflows processing untrusted user inputs
- ❌ Workflows from external/untrusted sources

#### Tool Loading Architecture

**Two Tool Types** (`src/strands_cli/runtime/tools.py`):
1. **@tool decorated functions**: Returns function object directly
2. **Module-based tools**: Returns module with `TOOL_SPEC` attribute

The CLI automatically detects which type and loads appropriately:
```python
if hasattr(module, "TOOL_SPEC"):
    return module  # Module-based tool (e.g., file_write)
else:
    return callable_obj  # @tool decorated function
```

**Detection & Logging**:
```python
# Disallowed tool attempts logged at WARNING level
logger.warning(
    "tool_blocked",
    violation_type="disallowed_python_callable",
    attempted_callable=callable_path,
    allowlist=ALLOWED_PYTHON_CALLABLES,
)
```

**What's Allowed**:
- Allowlisted tools only (see list above)
- String format: `["strands_tools.calculator.calculator"]`
- Dict format: `[{"callable": "strands_tools.calculator.calculator"}]`

**What's Blocked**:
- Any Python callable not in allowlist
- Arbitrary imports like `os.system`, `subprocess.run`
- Tools with old path format (migration required)

### Best Practices

**Development/Testing**:
```bash
# Interactive mode (prompts for file_write consent)
strands run workflow.yaml
```

**Production/CI**:
```bash
# Review spec for file_write tool usage first
strands validate workflow.yaml

# Run with bypass only after review
strands run workflow.yaml --bypass-tool-consent --force
```

**Audit file operations**:
```bash
# Enable structured logging to track file_write operations
export STRANDS_LOG_LEVEL=INFO
export STRANDS_LOG_FORMAT=json
strands run workflow.yaml 2>&1 | grep file_write
```

---

## Audit Logging

All security violations are logged using `structlog` with structured fields for analysis:

### Log Format
```json
{
  "event": "template_security_violation",
  "violation_type": "unsafe_operation",
  "error": "SecurityError: access to attribute '__class__' of 'str' object is unsafe",
  "template_preview": "{{ ''.__class__ }}",
  "timestamp": "2025-11-06T05:03:46Z",
  "level": "warning"
}
```

### Violation Types
- `template_security_violation`: Template sandbox escape attempt
- `http_url_blocked`: SSRF attempt (localhost, metadata endpoint, etc.)
- `artifact_path_blocked`: Path traversal or absolute path attempt
- `tool_blocked`: Disallowed Python callable attempt

### Log Levels
- **WARNING**: Security policy violation (blocked before execution)
- **ERROR**: Unexpected security failure
- **INFO**: Normal operations (not security-related)

---

## Configuration Best Practices

### Development/Testing
```bash
# Allow localhost for local testing
export STRANDS_HTTP_ALLOWED_DOMAINS='["^http://localhost"]'

# Run with interactive file_write consent
strands run workflow.yaml
```

### Production
```bash
# Enforce strict allowlist
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\\.openai\\.com", "^https://api\\.anthropic\\.com"]'

# Block additional internal patterns
export STRANDS_HTTP_BLOCKED_PATTERNS='["^https://.*\\.internal\\.company\\.com"]'

# Review workflow before bypassing tool consent
strands validate workflow.yaml
strands run workflow.yaml --bypass-tool-consent --force

# Review security logs
export STRANDS_LOG_LEVEL=WARNING
export STRANDS_LOG_FORMAT=json
```

### CI/CD
```bash
# Run specs from untrusted sources with maximum restrictions
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\\.trusted\\.com"]'

# Review for dangerous tools
grep -E "file_write|http_request" workflow.yaml

# Never use --bypass-tool-consent for untrusted specs
# Never use --force flag (prevent artifact overwrites)
strands run untrusted-spec.yaml
```

---

## Threat Model

### In Scope
- **User-editable workflow specs**: Assumes specs may be malicious (YAML/JSON from untrusted sources)
- **Template injection**: Prevents code execution via Jinja2 templates
- **SSRF attacks**: Prevents internal network scanning and metadata access
- **Path traversal**: Prevents file overwrite and directory escape
- **Data exfiltration**: Limits HTTP executor targets via allowlist/blocklist
- **Dangerous tool usage**: Allowlist restricts Python callables; file_write requires consent

### Out of Scope (Future Work)
- **Dependency confusion**: Python tool imports are allowlisted but not package-pinned
- **Resource exhaustion**: No rate limiting on LLM calls (budgets logged only)
- **Secrets exposure**: Env-only secrets assumed secure (Secrets Manager support planned)
- **Supply chain**: MCP servers not validated (future hardening needed)
- **File operation sandboxing**: file_write can write anywhere writable; no chroot/jail

---

## Security Updates

### Reporting Vulnerabilities
Report security issues to: [maintainer contact - TBD]

### Version History
- **v0.5.0**: Expanded Python tool allowlist (added file_write, calculator, current_time); added --bypass-tool-consent flag; improved tool loading architecture
- **v0.4.0**: Initial security hardening (Jinja2 sandbox, HTTP validation, path security)
- **v0.3.0**: Multi-agent support (no security hardening)
- **v0.2.0**: Single-agent MVP

---

## Future Enhancements

1. **Content Security Policy** for HTTP responses (validate Content-Type, size limits)
2. **MCP Server Sandboxing** (isolate MCP processes, allowlist executables)
3. **Rate Limiting** (enforce budget limits, prevent runaway costs)
4. **Secrets Manager Integration** (replace env-only secrets with secure vaults)
5. **Python Tool Sandboxing** (chroot/jail for file operations, restrict network access)
6. **Symlink Policy Refinement** (allow symlinks within output_dir after validation)
7. **Tool Package Pinning** (pin versions of strands_tools dependencies)

---

## Testing

Security features are covered by comprehensive negative tests:

- **Template Security**: 9 tests blocking introspection, eval, import
- **HTTP Security**: 14 tests blocking SSRF vectors and validating env vars
- **Path Security**: 7 tests blocking traversal, absolute paths, symlinks
- **Tool Security**: 5 tests validating allowlist enforcement and tool loading

Run security tests:
```bash
uv run pytest tests/test_executor.py::TestTemplateSecurity -v
uv run pytest tests/test_runtime.py::TestHttpExecutorSecurity -v
uv run pytest tests/test_executor.py::TestArtifactPathSecurity -v
uv run pytest tests/test_capability.py::TestCapabilityChecker::test_check_python_tools -v
```

---

## Summary

Strands CLI implements defense-in-depth for user-editable workflow specs:
1. **Templates** → Sandboxed Jinja2 (no code execution)
2. **HTTP Executors** → URL validation (no SSRF)
3. **Artifact Paths** → Multi-layer checks (no path traversal)
4. **Python Tools** → Allowlist + user consent for dangerous operations
5. **Audit Logging** → Structured security events

All violations logged at WARNING level with actionable context for operators.
