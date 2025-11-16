# Security Model

This document explains Strands CLI's defense-in-depth security architecture, threat model, security controls, and best practices for secure workflow execution.

## Security Philosophy

**Core Principle**: Treat all user-provided workflow specifications as potentially malicious.

**Design Approach**: Defense-in-depth with multiple security layers:
1. **Input Validation**: JSON Schema validation before execution
2. **Template Sandboxing**: Jinja2 sandbox prevents code injection
3. **SSRF Prevention**: URL validation for HTTP executors
4. **Path Security**: Multi-layer checks for artifact paths
5. **Tool Allowlisting**: Strict callable restrictions
6. **Audit Logging**: Structured security event logging

**Threat Model**: Workflows from untrusted sources (external users, compromised repos, malicious CI/CD pipelines).

---

## Threat Landscape

### Attack Surface

| Component | User Control | Attack Vector |
|-----------|--------------|---------------|
| **Templates** | Jinja2 expressions in prompts, inputs, artifact paths | Remote Code Execution (RCE) |
| **HTTP Executors** | `base_url` in tool config | Server-Side Request Forgery (SSRF) |
| **Artifact Paths** | Output file paths with templates | Path Traversal, File Overwrite |
| **Python Tools** | `callable` in tool config | Arbitrary Code Execution |
| **Variables** | CLI `--var` overrides | Template Injection, XSS |

### Threat Actors

1. **External Users**: Submit malicious workflow specs via web interface
2. **Compromised Repositories**: Specs from untrusted Git repos
3. **Supply Chain Attacks**: Malicious dependencies in Python tools
4. **Insider Threats**: Malicious specs from internal users

### Attack Scenarios

**Scenario 1: Template Injection for RCE**
```yaml
outputs:
  artifacts:
    - path: "{{ ''.__class__.__mro__[1].__subclasses__()[104].__init__.__globals__['os'].system('whoami') }}"
      from: "{{ last_response }}"
```
**Impact**: Remote code execution on host system

**Scenario 2: SSRF to Cloud Metadata**
```yaml
tools:
  http_executors:
    - id: "metadata"
      base_url: "http://169.254.169.254/latest/meta-data/"
```
**Impact**: Steal AWS credentials, compromise cloud account

**Scenario 3: Path Traversal for System File Overwrite**
```yaml
outputs:
  artifacts:
    - path: "../../etc/passwd"
      from: "malicious:content"
```
**Impact**: Overwrite system files, privilege escalation

**Scenario 4: Arbitrary Code Execution via Python Tools**
```yaml
tools:
  python:
    - callable: "os.system"
```
**Impact**: Execute arbitrary shell commands

---

## Security Layer 1: Template Sandboxing

### Risk: Remote Code Execution via Jinja2

**Vulnerability**: Jinja2 templates support Python introspection, allowing access to internal objects:
```python
{{ ''.__class__.__mro__[1].__subclasses__() }}  # Access all Python classes
{{ config.__class__.__init__.__globals__['os'].system('cmd') }}  # Execute commands
```

### Mitigation: SandboxedEnvironment

**Implementation** (`loader/template.py`):
```python
from jinja2.sandbox import SandboxedEnvironment

# Create sandboxed environment
env = SandboxedEnvironment(
    autoescape=False,  # Don't escape (not HTML context)
    undefined=StrictUndefined  # Raise error on undefined variables
)

# Whitelist only safe filters
env.filters = {
    "truncate": truncate_filter,
    "tojson": tojson_filter,
    "title": title_filter,
}

# Clear all globals (block builtin access)
env.globals.clear()
```

**What's Blocked**:
- Attribute access to `__class__`, `__mro__`, `__subclasses__`, `__globals__`, `__builtins__`
- Non-whitelisted filters (e.g., `upper`, `lower`, `replace`)
- Function calls via `()` syntax (except whitelisted filters)
- Import statements (`{% import %}`)
- Code blocks (`{% exec %}`, `{% eval %}`)

**What's Allowed**:
- Variable expansion: `{{ topic }}`, `{{ steps[0].response }}`
- Whitelisted filters: `{{ text | truncate(100) }}`, `{{ data | tojson }}`, `{{ topic | title }}`
- Dictionary access: `{{ inputs.topic }}`, `{{ tasks.research.response }}`
- List indexing: `{{ steps[0].response }}`, `{{ branches[1].response }}`

**Security Tests** (`tests/test_executor.py`):
```python
def test_template_blocks_class_introspection():
    """Template sandbox blocks __class__ access."""
    spec = create_spec(artifact_path="{{ ''.__class__ }}")
    with pytest.raises(SecurityError, match="unsafe"):
        render_template(spec)

def test_template_blocks_builtins():
    """Template sandbox blocks builtin access."""
    spec = create_spec(artifact_path="{{ __builtins__ }}")
    with pytest.raises(SecurityError, match="unsafe"):
        render_template(spec)
```

**Audit Logging**:
```json
{
  "event": "template_security_violation",
  "violation_type": "unsafe_operation",
  "error": "SecurityError: access to attribute '__class__' is unsafe",
  "template_preview": "{{ ''.__class__ }}",
  "timestamp": "2025-11-09T05:03:46Z",
  "level": "warning"
}
```

### Best Practices

**✅ Safe Template Usage**:
```yaml
# Variable expansion
prompt: "Research {{ topic }}"

# Whitelisted filters
prompt: "Summarize: {{ long_text | truncate(500) }}"

# JSON serialization
prompt: "Analyze data: {{ data | tojson }}"

# Title case
prompt: "Write about {{ topic | title }}"
```

**❌ Unsafe Patterns** (will raise SecurityError):
```yaml
# Introspection
prompt: "{{ object.__class__ }}"

# Builtin access
prompt: "{{ __import__('os') }}"

# Non-whitelisted filters
prompt: "{{ text | upper }}"  # Not in whitelist

# Code execution
prompt: "{% exec malicious_code %}"
```

---

## Security Layer 2: SSRF Prevention

### Risk: Server-Side Request Forgery

**Vulnerability**: HTTP executors allow arbitrary `base_url` values, enabling attacks on:
- Internal services (databases, APIs)
- Cloud metadata endpoints (AWS, Azure, GCP)
- Localhost services (SSH, databases)
- File system (`file://` protocol)

**Attack Example**:
```yaml
tools:
  http_executors:
    - id: "metadata"
      base_url: "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
# Steal AWS credentials from metadata endpoint
```

### Mitigation: URL Validation with Blocklist/Allowlist

**Default Blocked Patterns** (`types.py`):
```python
DEFAULT_BLOCKED_URL_PATTERNS = [
    r"^https?://127\.0\.0\.1.*$",        # Localhost IPv4
    r"^https?://localhost.*$",           # Localhost hostname
    r"^https?://\[::1\].*$",             # Localhost IPv6
    r"^https?://169\.254\.169\.254.*$",  # AWS/Azure metadata
    r"^https?://10\..*$",                # RFC1918 private (10.0.0.0/8)
    r"^https?://172\.(1[6-9]|2\d|3[01])\..*$",  # RFC1918 (172.16.0.0/12)
    r"^https?://192\.168\..*$",          # RFC1918 private (192.168.0.0/16)
    r"^file:///.*$",                     # File protocol
    r"^ftp://.*$",                       # FTP protocol
    r"^gopher://.*$",                    # Gopher protocol
]
```

**Implementation** (`types.py`):
```python
class HttpExecutor(BaseModel):
    """HTTP executor configuration with SSRF protection."""
    
    id: str
    base_url: str
    timeout: int = 30
    
    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL against blocklist and allowlist."""
        # Load config
        config = Settings()
        blocked = DEFAULT_BLOCKED_URL_PATTERNS + config.http_blocked_patterns
        allowed = config.http_allowed_domains
        
        # If allowlist exists, only allow matching URLs
        if allowed:
            if not any(re.match(pattern, v) for pattern in allowed):
                raise ValueError(f"URL not in allowlist: {v}")
        
        # Block URLs matching blocklist
        for pattern in blocked:
            if re.match(pattern, v):
                logger.warning(
                    "http_url_blocked",
                    violation_type="ssrf_attempt",
                    blocked_url=v,
                    matched_pattern=pattern,
                )
                raise ValueError(f"URL blocked by pattern: {pattern}")
        
        return v
```

**Environment Configuration**:
```bash
# Add custom blocked patterns
export STRANDS_HTTP_BLOCKED_PATTERNS='["^https://internal-api\\.company\\.com"]'

# Enforce strict allowlist (blocks all except matches)
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\\.openai\\.com", "^https://.*\\.trusted\\.com"]'
```

**What's Blocked by Default**:
- Localhost/loopback: `127.0.0.1`, `localhost`, `[::1]`
- Private networks: `10.x.x.x`, `172.16-31.x.x`, `192.168.x.x`
- Cloud metadata: `169.254.169.254` (AWS/Azure), `metadata.google.internal` (GCP via custom pattern)
- Non-HTTP protocols: `file://`, `ftp://`, `gopher://`

**What's Allowed by Default**:
- Public HTTP/HTTPS URLs: `https://api.openai.com`, `http://example.com`

**Security Tests** (`tests/test_runtime.py`):
```python
def test_http_executor_blocks_localhost():
    """HTTP executor blocks localhost URLs."""
    spec = {
        "tools": {
            "http_executors": [
                {"id": "test", "base_url": "http://localhost:8000"}
            ]
        }
    }
    with pytest.raises(ValidationError, match="blocked"):
        Spec(**spec)

def test_http_executor_blocks_aws_metadata():
    """HTTP executor blocks AWS metadata endpoint."""
    spec = {
        "tools": {
            "http_executors": [
                {"id": "test", "base_url": "http://169.254.169.254/latest/"}
            ]
        }
    }
    with pytest.raises(ValidationError, match="blocked"):
        Spec(**spec)
```

### Best Practices

**✅ Safe HTTP Executor Usage**:
```yaml
# Public APIs
tools:
  http_executors:
    - id: "openai"
      base_url: "https://api.openai.com"
    - id: "github"
      base_url: "https://api.github.com"
```

**✅ Development with Localhost** (override blocklist):
```bash
# Allow localhost for local testing
export STRANDS_HTTP_ALLOWED_DOMAINS='["^http://localhost"]'
strands run workflow.yaml
```

**❌ Unsafe Patterns** (will raise ValidationError):
```yaml
# Localhost
tools:
  http_executors:
    - base_url: "http://localhost:5000"

# AWS metadata
tools:
  http_executors:
    - base_url: "http://169.254.169.254/latest/"

# Private network
tools:
  http_executors:
    - base_url: "http://192.168.1.100/admin"
```

---

## Security Layer 3: Path Traversal Protection

### Risk: File Overwrite and Directory Escape

**Vulnerability**: Artifact paths support templates that can render user variables, enabling:
- Path traversal (`../../etc/passwd`)
- Absolute paths (`/etc/passwd`, `C:\Windows\System32\config`)
- Symlink attacks (follow symlinks outside output directory)

**Attack Example**:
```yaml
outputs:
  artifacts:
    - path: "{{ malicious_path }}"
      from: "{{ last_response }}"
```
```bash
strands run workflow.yaml --var malicious_path="../../etc/passwd"
```

### Mitigation: Multi-Layer Path Validation

**Implementation** (`artifacts/io.py`):
```python
def write_artifact(artifact: Artifact, content: str, output_dir: Path) -> None:
    """Write artifact with multi-layer path security."""
    # 1. Reject absolute paths
    path_obj = Path(artifact.path)
    if path_obj.is_absolute():
        raise ArtifactError(
            f"Absolute paths not allowed: {artifact.path}",
            violation_type="absolute_path"
        )
    
    # 2. Block path traversal (..) components
    if ".." in path_obj.parts:
        raise ArtifactError(
            f"Path traversal not allowed: {artifact.path}",
            violation_type="path_traversal"
        )
    
    # 3. Sanitize path components
    sanitized_parts = [sanitize_filename(part) for part in path_obj.parts]
    sanitized_path = Path(*sanitized_parts)
    
    # 4. Validate resolved path (prevent symlink escape)
    artifact_path = (output_dir / sanitized_path).resolve()
    try:
        artifact_path.relative_to(output_dir.resolve())
    except ValueError:
        raise ArtifactError(
            f"Path escapes output directory: {artifact.path}",
            violation_type="directory_escape"
        )
    
    # 5. Block symlinks (MVP restriction)
    if artifact_path.is_symlink():
        raise ArtifactError(
            f"Symlinks not allowed: {artifact.path}",
            violation_type="symlink"
        )
    
    # Write artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(content, encoding="utf-8")
```

**Sanitization** (`artifacts/io.py`):
```python
def sanitize_filename(filename: str) -> str:
    """Sanitize filename component.
    
    Removes:
    - Path separators (/, \)
    - Control characters
    - Leading/trailing dots and underscores
    
    Replaces with underscore:
    - Special characters (<, >, :, ", |, ?, *)
    """
    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")
    
    # Replace special characters
    filename = re.sub(r'[<>:"|?*]', "_", filename)
    
    # Remove control characters
    filename = "".join(c for c in filename if ord(c) >= 32)
    
    # Strip leading/trailing dots and underscores
    filename = filename.strip("._")
    
    return filename or "output"  # Fallback if empty
```

**What's Blocked**:
- Absolute paths: `/etc/passwd`, `C:\Windows\hosts`
- Path traversal: `../../etc/passwd`, `..\..\..\windows\hosts`
- Symlinks: Any symlink (MVP restriction)
- Special characters: `<>:"|?*` in filenames

**What's Allowed**:
- Relative paths: `output.txt`, `reports/summary.md`
- Nested directories: `analysis/data/results.json`
- Template variables: `{{ spec.name }}-report.txt`

**Security Tests** (`tests/test_executor.py`):
```python
def test_artifact_blocks_path_traversal():
    """Artifact writing blocks path traversal."""
    artifact = Artifact(path="../../etc/passwd", from_="data")
    with pytest.raises(ArtifactError, match="traversal"):
        write_artifact(artifact, "content", Path("./artifacts"))

def test_artifact_blocks_absolute_path():
    """Artifact writing blocks absolute paths."""
    artifact = Artifact(path="/etc/passwd", from_="data")
    with pytest.raises(ArtifactError, match="absolute"):
        write_artifact(artifact, "content", Path("./artifacts"))
```

### Best Practices

**✅ Safe Artifact Paths**:
```yaml
outputs:
  artifacts:
    # Simple filename
    - path: "output.txt"
      from: "{{ last_response }}"
    
    # Nested directory
    - path: "reports/{{ spec.name }}.md"
      from: "{{ last_response }}"
    
    # Timestamp in filename
    - path: "analysis-{{ timestamp }}.json"
      from: "{{ tasks.analysis.response | tojson }}"
```

**❌ Unsafe Patterns** (will raise ArtifactError):
```yaml
# Path traversal
outputs:
  artifacts:
    - path: "../../etc/passwd"

# Absolute path
outputs:
  artifacts:
    - path: "/etc/passwd"

# Symlink (if exists)
outputs:
  artifacts:
    - path: "symlink-to-system-file"
```

---

## Security Layer 4: Tool Allowlisting

### Risk: Arbitrary Code Execution

**Vulnerability**: Python tools execute arbitrary callables, enabling:
- System command execution (`os.system`, `subprocess.run`)
- File operations (`open`, `shutil.rmtree`)
- Network access (`socket`, `urllib`)
- Dynamic imports (`__import__`, `importlib`)

**Attack Example**:
```yaml
tools:
  python:
    - callable: "os.system"  # Execute arbitrary commands
```

### Mitigation: Strict Allowlist + User Consent

**Allowlisted Callables** (`capability/checker.py`):
```python
# Native tools are allowlisted via registry auto-discovery
registry = get_registry()
allowed = registry.get_allowlist()
# Returns: {"http_request", "file_read", "file_write", "calculator", "current_time", ...}
```

**Capability Checking** (`capability/checker.py`):
```python
def check_python_tools(spec: Spec) -> list[UnsupportedFeature]:
    """Check if Python tools are in allowlist."""
    issues = []
    
    for tool in spec.tools.python:
        callable_path = tool.callable
        if callable_path not in ALLOWED_PYTHON_CALLABLES:
            issues.append(UnsupportedFeature(
                category="tools.python",
                feature=callable_path,
                remediation=f"Use allowlisted tool. Allowed: {ALLOWED_PYTHON_CALLABLES}",
                severity="high"
            ))
    
    return issues
```

**User Consent for file_write** (`strands_tools.file_write`):
```python
def file_write(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Write file with user consent (unless bypassed)."""
    tool_input = tool.get("input", {})
    file_path = tool_input.get("file_path")
    content = tool_input.get("content")
    
    # Check bypass flag
    if not os.environ.get("BYPASS_TOOL_CONSENT"):
        # Prompt for consent
        print(f"File write requested: {file_path}")
        print(f"Content preview: {content[:100]}...")
        response = input("Allow? (y/N): ")
        
        if response.lower() != "y":
            return {
                "toolUseId": tool.get("toolUseId"),
                "status": "error",
                "content": [{"text": "User denied file write"}]
            }
    
    # Write file
    Path(file_path).write_text(content)
    return {"toolUseId": tool.get("toolUseId"), "status": "success", ...}
```

**Bypass for Automation** (CLI flag):
```bash
# Interactive mode (default)
strands run workflow.yaml
# Prompts for file_write consent

# CI/CD mode (bypass consent)
strands run workflow.yaml --bypass-tool-consent
# Sets BYPASS_TOOL_CONSENT=true, skips prompts
```

**What's Allowed**:
- `strands_tools.http_request` - HTTP requests (subject to SSRF protection)
- `strands_tools.file_read` - Read files (read-only)
- `strands_tools.file_write` - Write files (requires consent)
- `strands_tools.calculator` - Mathematical calculations
- `strands_tools.current_time` - Get current date/time

**What's Blocked**:
- `os.system`, `subprocess.run` - Command execution
- `eval`, `exec`, `compile` - Code evaluation
- `open`, `shutil.rmtree` - Direct file operations
- `socket`, `urllib` - Direct network access
- Any callable not in allowlist

**Security Tests** (`tests/test_capability.py`):
```python
def test_capability_blocks_disallowed_python_tool():
    """Capability checker blocks disallowed Python callables."""
    spec = create_spec(
        tools={"python": [{"callable": "os.system"}]}
    )
    report = check_capability(spec)
    assert not report.supported
    assert any("os.system" in issue.feature for issue in report.issues)
```

### Best Practices

**✅ Safe Tool Usage**:
```yaml
# HTTP requests
tools:
  python:
    - callable: "strands_tools.http_request.http_request"

# File reading
tools:
  python:
    - callable: "strands_tools.file_read.file_read"
```

**✅ CI/CD with Bypass** (after review):
```bash
# Review spec for dangerous tools
grep -E "file_write|system|exec" workflow.yaml

# Run with bypass only after review
strands run workflow.yaml --bypass-tool-consent --force
```

**❌ Unsafe Patterns** (will trigger EX_UNSUPPORTED):
```yaml
# Arbitrary code execution
tools:
  python:
    - callable: "os.system"

# Direct file operations
tools:
  python:
    - callable: "open"
```

---

## Audit Logging

All security violations are logged with structured fields for SIEM integration.

### Log Format

**JSON Structured Logs** (`STRANDS_LOG_FORMAT=json`):
```json
{
  "event": "http_url_blocked",
  "violation_type": "ssrf_attempt",
  "blocked_url": "http://169.254.169.254/latest/",
  "matched_pattern": "^https?://169\\.254\\.169\\.254.*$",
  "timestamp": "2025-11-09T05:03:46Z",
  "level": "warning",
  "spec_file": "/path/to/workflow.yaml",
  "user": "alice"
}
```

### Violation Types

| Event | Violation Type | Severity | Action |
|-------|----------------|----------|--------|
| `template_security_violation` | `unsafe_operation` | High | Block template rendering |
| `http_url_blocked` | `ssrf_attempt` | High | Block HTTP executor creation |
| `artifact_path_blocked` | `path_traversal` | High | Block artifact write |
| `tool_blocked` | `disallowed_callable` | Critical | Exit with EX_UNSUPPORTED |

### Integration with SIEM

**Export to CloudWatch Logs** (AWS):
```bash
# Configure log group
export STRANDS_LOG_GROUP="/aws/strands-cli/security"

# Run with CloudWatch export
strands run workflow.yaml --log-cloudwatch
```

**Export to S3** (archival):
```bash
# Configure S3 bucket
export STRANDS_LOG_S3_BUCKET="security-audit-logs"

# Run with S3 export
strands run workflow.yaml --log-s3
```

**Query with CloudWatch Insights**:
```sql
fields @timestamp, event, violation_type, blocked_url
| filter event = "http_url_blocked"
| sort @timestamp desc
| limit 100
```

---

## Security Best Practices

### Development

**✅ Test with Restricted Settings**:
```bash
# Block all except specific domains
export STRANDS_HTTP_ALLOWED_DOMAINS='["^http://localhost", "^https://httpbin.org"]'

# Run workflow
strands run workflow.yaml
```

**✅ Use Interactive Mode for file_write**:
```bash
# Default behavior (prompts for consent)
strands run workflow.yaml
```

**✅ Review Logs for Violations**:
```bash
# Enable JSON logging
export STRANDS_LOG_FORMAT=json
export STRANDS_LOG_LEVEL=WARNING

# Run and filter security events
strands run workflow.yaml 2>&1 | jq 'select(.event | contains("blocked"))'
```

### Production

**✅ Enforce Strict Allowlist**:
```bash
# Only allow trusted domains
export STRANDS_HTTP_ALLOWED_DOMAINS='["^https://api\\.openai\\.com", "^https://api\\.anthropic\\.com"]'
```

**✅ Add Custom Blocklist**:
```bash
# Block internal infrastructure
export STRANDS_HTTP_BLOCKED_PATTERNS='["^https://.*\\.internal\\.company\\.com", "^https://admin\\..*"]'
```

**✅ Review Specs Before Execution**:
```bash
# Validate schema
strands validate untrusted-spec.yaml

# Check for dangerous tools
grep -E "file_write|http_request|os\\.system" untrusted-spec.yaml

# Review template expressions
grep -E "\\{\\{.*__class__.*\\}\\}" untrusted-spec.yaml
```

**✅ Use `--bypass-tool-consent` Only After Review**:
```bash
# ONLY for reviewed specs in CI/CD
strands run reviewed-spec.yaml --bypass-tool-consent --force
```

**❌ Never Use `--bypass-tool-consent` for Untrusted Specs**:
```bash
# DANGEROUS: Untrusted spec with consent bypass
strands run untrusted-spec.yaml --bypass-tool-consent  # DON'T DO THIS
```

### CI/CD

**✅ Isolated Execution Environment**:
```yaml
# GitHub Actions example
jobs:
  run-workflow:
    runs-on: ubuntu-latest
    container:
      image: python:3.12-slim
      options: --read-only --tmpfs /tmp  # Read-only filesystem
    steps:
      - name: Run workflow
        run: strands run workflow.yaml --bypass-tool-consent
```

**✅ Limit Network Access**:
```yaml
# Docker Compose example
services:
  strands-cli:
    image: strands-cli:latest
    networks:
      - restricted  # Custom network with egress filtering
    environment:
      STRANDS_HTTP_ALLOWED_DOMAINS: '["^https://api\\.openai\\.com"]'
```

**✅ Monitor Security Events**:
```yaml
# GitHub Actions example
- name: Check for security violations
  run: |
    strands run workflow.yaml 2>&1 | tee logs.json
    if grep -q "violation_type" logs.json; then
      echo "Security violations detected!"
      exit 1
    fi
```

---

## Future Enhancements

### Planned Security Features

1. **Content Security Policy** for HTTP responses
   - Validate `Content-Type` headers
   - Enforce size limits
   - Block binary responses (unless expected)

2. **MCP Server Sandboxing**
   - Isolate MCP processes (chroot, Docker)
   - Allowlist MCP executables
   - Resource limits (CPU, memory, network)

3. **Rate Limiting**
   - Enforce budget limits (prevent runaway costs)
   - Per-provider rate limits
   - Circuit breaker for failing services

4. **Secrets Manager Integration**
   - AWS Secrets Manager / SSM support
   - HashiCorp Vault integration
   - Encrypted secrets in specs

5. **Python Tool Sandboxing**
   - Chroot/jail for file operations
   - Network access restrictions
   - Syscall filtering (seccomp)

6. **Symlink Policy Refinement**
   - Allow symlinks within `output_dir` (after validation)
   - Detect symlink loops
   - Prevent time-of-check-time-of-use (TOCTOU) attacks

---

## Summary

Strands CLI implements defense-in-depth security:

1. **Template Sandboxing**: Jinja2 SandboxedEnvironment prevents RCE
2. **SSRF Prevention**: URL validation blocks localhost, metadata, private IPs
3. **Path Security**: Multi-layer checks prevent traversal and overwrite
4. **Tool Allowlisting**: Strict callable restrictions prevent arbitrary code execution
5. **Audit Logging**: Structured security events for SIEM integration

**Security Posture**:
- ✅ Threat model: Untrusted workflow specs
- ✅ Attack surface: Templates, HTTP, paths, tools
- ✅ Security controls: Multi-layer validation, sandboxing, allowlisting
- ✅ Audit trail: Structured logging of all violations

**Best Practices**:
- Review specs before execution (especially from untrusted sources)
- Use allowlist/blocklist environment variables for production
- Enable structured logging for security monitoring
- Use `--bypass-tool-consent` only for reviewed specs in CI/CD
- Monitor audit logs for security violations

**Next Steps**: See [Architecture Overview](architecture.md), [Pattern Philosophy](patterns.md), [Design Decisions](design-decisions.md), and [Performance Optimizations](performance.md) for more details.
