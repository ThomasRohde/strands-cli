"""Typer commands for atomic agent workflows."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

from strands_cli.atomic.core import (
    ATOMIC_LABEL,
    ATOMIC_LABEL_VALUE,
    check_atomic_invariants,
    find_atomic_specs,
    resolve_atomic_spec,
)
from strands_cli.exit_codes import EX_IO, EX_OK, EX_RUNTIME, EX_SCHEMA, EX_USAGE
from strands_cli.loader import LoadError, load_spec
from strands_cli.schema import SchemaValidationError
from strands_cli.exec.single_agent import run_single_agent
from strands_cli.types import Spec

console = Console()

atomic_app = typer.Typer(
    name="atomic",
    help="Work with atomic agent manifests (list, describe, validate).",
    add_completion=False,
    pretty_exceptions_enable=False,
)


def _path_is_under_atomic(path: Path) -> bool:
    """Return True if the path lives under agents/atomic/."""
    parts = [p.lower() for p in path.resolve().parts]
    if "agents" not in parts or "atomic" not in parts:
        return False
    try:
        agents_idx = parts.index("agents")
        atomic_idx = parts.index("atomic", agents_idx)
        return atomic_idx > agents_idx
    except ValueError:
        return False


def _load_metadata(path: Path) -> dict[str, Any]:
    """Lightweight metadata loader for YAML manifests."""
    yaml = YAML(typ="safe", pure=True)
    try:
        data = yaml.load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    meta = data.get("metadata") or {}
    return meta if isinstance(meta, dict) else {}


def _infer_name(path: Path, metadata: dict[str, Any]) -> str:
    meta_name = metadata.get("name")
    if isinstance(meta_name, str) and meta_name.strip():
        return meta_name.strip()
    return path.stem


def _resolve_manifest(target: str) -> Path:
    """Resolve a manifest by path or name."""
    candidate = Path(target)
    if candidate.exists():
        return candidate

    resolved = resolve_atomic_spec(target, Path.cwd())
    if resolved:
        return resolved

    console.print(f"[red]Atomic manifest not found for '{target}'[/red]")
    raise typer.Exit(EX_USAGE)


def _agent_label(metadata: dict[str, Any]) -> str:
    labels = metadata.get("labels")
    if isinstance(labels, dict):
        return str(labels.get(ATOMIC_LABEL, "unknown"))
    return "unknown"


def _collect_list_entries(root: Path, include_all: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    candidates = (
        set(find_atomic_specs(root))
        if not include_all
        else set(root.glob("agents/**/*.yaml")).union(set(root.glob("agents/**/*.yml")))
    )

    for path in sorted(candidates):
        metadata = _load_metadata(path)
        labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}

        if not include_all:
            # Atomic detection by location or label
            if not (_path_is_under_atomic(path) or labels.get(ATOMIC_LABEL) == ATOMIC_LABEL_VALUE):
                continue

        entry = {
            "name": _infer_name(path, metadata),
            "path": str(path.relative_to(root)),
            "agent_type": labels.get(ATOMIC_LABEL, "unknown"),
            "domain": labels.get("strands.io/domain") if labels else None,
            "capability": labels.get("strands.io/capability") if labels else None,
            "version": labels.get("strands.io/version") if labels else None,
        }
        results.append(entry)

    return results


def _print_list(entries: list[dict[str, Any]]) -> None:
    if not entries:
        console.print("[yellow]No atomic agents found[/yellow]")
        return

    table = Table(title="Atomic Agents", border_style="cyan")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Path", style="dim")
    table.add_column("Type", style="magenta")
    table.add_column("Domain", style="white")
    table.add_column("Capability", style="white")
    table.add_column("Version", style="white")

    for entry in entries:
        table.add_row(
            entry["name"],
            entry["path"],
            entry.get("agent_type") or "",
            entry.get("domain") or "",
            entry.get("capability") or "",
            entry.get("version") or "",
        )

    console.print()
    console.print(table)


def _validate_contract_files(spec: Spec, manifest_path: Path) -> list[str]:
    """Ensure referenced schema files exist on disk."""
    errors: list[str] = []

    agents = list(spec.agents.values())
    if not agents:
        return ["Spec has no agents"]

    agent = agents[0]
    for field_name, schema_value in (("input_schema", agent.input_schema), ("output_schema", agent.output_schema)):
        if schema_value is None or isinstance(schema_value, dict):
            continue
        schema_path = Path(schema_value)
        if not schema_path.is_absolute():
            schema_path = manifest_path.parent / schema_path
        if not schema_path.exists():
            errors.append(f"{field_name} not found at {schema_path}")

    return errors


def _load_schema(schema_ref: str | dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    """Load JSON schema from a path or return inline dict."""
    if isinstance(schema_ref, dict):
        return schema_ref

    schema_path = Path(schema_ref)
    if not schema_path.is_absolute():
        schema_path = manifest_path.parent / schema_path
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise LoadError(f"Failed to read schema {schema_path}: {e}") from e


def _validate_json_schema(payload: Any, schema: dict[str, Any], label: str) -> list[str]:
    """Validate payload against schema and return error messages."""
    validator = Draft202012Validator(schema)
    return [f"{label}: {err.message} at /{'/'.join([str(p) for p in err.path])}" for err in validator.iter_errors(payload)]


def _validate_input_schema(agent: Any, manifest_path: Path, raw_input: dict[str, Any]) -> list[str]:
    """Validate raw input against agent input_schema if present."""
    if not agent.input_schema:
        return []
    schema = _load_schema(agent.input_schema, manifest_path)
    return _validate_json_schema(raw_input, schema, "input")


def _validate_output_schema(
    agent: Any, manifest_path: Path, response_text: str | None, override_schema: Any = None
) -> tuple[bool, Any, list[str]]:
    """Validate output text against schema (agent or override)."""
    if response_text is None:
        return True, None, []

    schema_ref = override_schema if override_schema is not None else agent.output_schema
    if not schema_ref:
        return True, response_text, []

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return False, response_text, ["Output is not valid JSON for schema validation"]

    schema = _load_schema(schema_ref, manifest_path)
    errors = _validate_json_schema(payload, schema, "output")
    return not errors, payload, errors


@atomic_app.command("list")
def list_atomic(
    all: bool = typer.Option(False, "--all", help="Include non-atomic manifests with labels"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List atomic agent manifests in the repository."""

    root = Path.cwd()
    entries = _collect_list_entries(root, include_all=all)

    if json_output:
        typer.echo(json.dumps(entries, indent=2))
        raise typer.Exit(code=EX_OK)

    _print_list(entries)


@atomic_app.command("describe")
def describe_atomic(
    name: str,
    format: str = typer.Option(
        "rich", "--format", "-f", help="Output format", case_sensitive=False
    ),
) -> None:
    """Describe an atomic manifest by name or path."""
    manifest_path = _resolve_manifest(name)

    try:
        spec = load_spec(str(manifest_path))
    except LoadError as e:
        console.print(f"[red]Failed to load spec: {e}[/red]")
        raise typer.Exit(EX_IO)
    except SchemaValidationError as e:
        console.print(f"[red]Schema validation failed: {e}[/red]")
        raise typer.Exit(EX_SCHEMA)

    invariants = check_atomic_invariants(spec)
    labels = spec.metadata.labels if spec.metadata and spec.metadata.labels else {}

    if format.lower() == "json":
        output = {
            "path": str(manifest_path),
            "name": spec.metadata.name if spec.metadata and spec.metadata.name else spec.name,
            "description": spec.metadata.description if spec.metadata else spec.description,
            "labels": labels,
            "runtime": spec.runtime.model_dump(),
            "agents": list(spec.agents.keys()),
            "input_schema": next(iter(spec.agents.values())).input_schema if spec.agents else None,
            "output_schema": next(iter(spec.agents.values())).output_schema if spec.agents else None,
            "invariant_errors": invariants,
        }
        typer.echo(json.dumps(output, indent=2))
        raise typer.Exit(EX_OK)

    if format.lower() == "yaml":
        yaml = YAML()
        typer.echo(yaml.dump(spec.model_dump()))
        raise typer.Exit(EX_OK)

    # Rich describe
    meta_panel = Panel.fit(
        f"[bold]{spec.metadata.name if spec.metadata and spec.metadata.name else spec.name}[/bold]\n"
        f"{spec.metadata.description or spec.description or ''}\n\n"
        f"[cyan]Path:[/cyan] {manifest_path}\n"
        f"[cyan]Agent Type:[/cyan] {labels.get(ATOMIC_LABEL, 'unknown')}\n"
        f"[cyan]Runtime:[/cyan] {spec.runtime.provider.value} / {spec.runtime.model_id or 'default'}\n"
        f"[cyan]Agents:[/cyan] {', '.join(spec.agents.keys())}",
        title="Atomic Agent",
        border_style="cyan",
    )

    console.print(meta_panel)

    if labels:
        label_table = Table(title="Labels", border_style="magenta")
        label_table.add_column("Key", style="dim")
        label_table.add_column("Value")
        for key, value in labels.items():
            label_table.add_row(key, value)
        console.print(label_table)

    if invariants:
        console.print("[red]Atomic invariant violations:[/red]")
        for err in invariants:
            console.print(f"  - {err}")


@atomic_app.command("run")
def run_atomic(
    name: str,
    input_file: Path = typer.Option(..., "--input-file", "-i", exists=True, readable=True),
    output_file: Path | None = typer.Option(None, "--output-file", "-o"),
) -> None:
    """Run an atomic agent with optional contract validation."""
    import asyncio

    manifest_path = _resolve_manifest(name)

    try:
        raw_input = json.loads(input_file.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]Failed to read input file: {e}[/red]")
        raise typer.Exit(EX_IO)

    if not isinstance(raw_input, dict):
        console.print("[red]Input file must contain a JSON object[/red]")
        raise typer.Exit(EX_USAGE)

    try:
        spec = load_spec(str(manifest_path), variables=raw_input)
    except LoadError as e:
        console.print(f"[red]Failed to load spec: {e}[/red]")
        raise typer.Exit(EX_IO)
    except SchemaValidationError as e:
        console.print(f"[red]Schema validation failed: {e}[/red]")
        raise typer.Exit(EX_SCHEMA)

    invariant_errors = check_atomic_invariants(spec)
    if invariant_errors:
        console.print("[red]Atomic invariant violations prevent execution:[/red]")
        for err in invariant_errors:
            console.print(f"  - {err}")
        raise typer.Exit(EX_USAGE)

    agent = next(iter(spec.agents.values()))

    try:
        input_errors = _validate_input_schema(agent, manifest_path, raw_input)
        if input_errors:
            console.print("[red]Input failed schema validation:[/red]")
            for err in input_errors:
                console.print(f"  - {err}")
            raise typer.Exit(EX_SCHEMA)
    except LoadError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(EX_IO)

    try:
        result = asyncio.run(run_single_agent(spec, variables=raw_input))
    except Exception as e:
        console.print(f"[red]Execution failed: {e}[/red]")
        raise typer.Exit(EX_RUNTIME)

    console.print("[green]Execution complete[/green]")
    if result.last_response:
        console.print(Panel(result.last_response, title="Output", border_style="green"))

    # Output schema validation
    output_valid = True
    output_payload: Any = result.last_response
    try:
        output_valid, output_payload, output_errors = _validate_output_schema(
            agent, manifest_path, result.last_response
        )
        if output_errors:
            output_valid = False
            console.print("[red]Output failed schema validation:[/red]")
            for err in output_errors:
                console.print(f"  - {err}")
    except LoadError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(EX_IO)

    if output_file:
        try:
            if isinstance(output_payload, (dict, list)):
                output_file.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
            else:
                output_file.write_text(str(result.last_response or ""), encoding="utf-8")
        except Exception as e:
            console.print(f"[red]Failed to write output file: {e}[/red]")
            raise typer.Exit(EX_IO)

    if not output_valid:
        raise typer.Exit(EX_RUNTIME)


def _load_test_cases(name: str, manifest_path: Path) -> tuple[Path, list[dict[str, Any]]]:
    """Load test case definitions."""
    root = Path.cwd()
    # Try new subdirectory structure first (agents/atomic/<name>/tests.yaml)
    agent_dir = root / "agents" / "atomic" / name
    candidates = [
        agent_dir / "tests.yaml",
        agent_dir / "tests.yml",
        # Fall back to legacy flat structure
        root / "tests" / f"{name}_tests.yaml",
        root / "tests" / f"{name}_tests.yml",
    ]
    test_path = next((p for p in candidates if p.exists()), None)
    if not test_path:
        raise LoadError(f"Test file not found: {candidates[0]}")

    yaml = YAML(typ="safe", pure=True)
    data = yaml.load(test_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LoadError("Test file must contain a mapping with 'tests' entries")

    cases = data.get("tests") or data.get("cases")
    if not isinstance(cases, list):
        raise LoadError("Test file missing 'tests' list")

    return test_path, cases


def _apply_checks(payload: Any, checks: list[dict[str, Any]]) -> list[str]:
    """Execute simple expectation checks on payload."""
    errors: list[str] = []
    for check in checks:
        ctype = check.get("type")
        if ctype == "has_keys":
            keys = check.get("keys", [])
            if not isinstance(payload, dict):
                errors.append("has_keys requires JSON object payload")
                continue
            missing = [k for k in keys if k not in payload]
            if missing:
                errors.append(f"Missing keys: {', '.join(missing)}")
        elif ctype == "max_length":
            field = check.get("field")
            limit = check.get("value")
            if field not in payload or not isinstance(limit, int):
                errors.append("max_length requires 'field' and integer 'value'")
                continue
            field_val = payload.get(field)
            if field_val is None:
                errors.append(f"Field '{field}' missing for max_length")
                continue
            if len(str(field_val)) > limit:
                errors.append(f"Field '{field}' exceeds max_length {limit}")
        elif ctype == "contains":
            expected = check.get("value")
            if expected not in str(payload):
                errors.append(f"Payload does not contain '{expected}'")
        # Additional checks can be added here
    return errors


@atomic_app.command("test")
def test_atomic(
    name: str,
    filter_pattern: str | None = typer.Option(None, "--filter", help="Only run cases containing substring"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON results"),
) -> None:
    """Run atomic agent tests from <name>_tests.yaml."""
    manifest_path = _resolve_manifest(name)

    try:
        test_path, cases = _load_test_cases(name, manifest_path)
    except LoadError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(EX_IO)

    results: list[dict[str, Any]] = []
    any_fail = False

    for case in cases:
        case_name = case.get("name", "unnamed")
        if filter_pattern and filter_pattern not in case_name:
            continue

        status = "pass"
        message = ""

        try:
            input_ref = case.get("input")
            if not input_ref:
                raise LoadError(f"Test '{case_name}' missing input")
            input_path = (test_path.parent / input_ref).resolve()
            if not input_path.exists():
                raise LoadError(f"Input file not found: {input_path}")
            raw_input = json.loads(input_path.read_text(encoding="utf-8"))
            if not isinstance(raw_input, dict):
                raise LoadError("Input must be a JSON object")

            spec = load_spec(str(manifest_path), variables=raw_input)
            agent = next(iter(spec.agents.values()))

            invariant_errors = check_atomic_invariants(spec)
            if invariant_errors:
                raise LoadError("; ".join(invariant_errors))

            input_errors = _validate_input_schema(agent, manifest_path, raw_input)
            if input_errors:
                raise LoadError("; ".join(input_errors))

            result = asyncio.run(run_single_agent(spec, variables=raw_input))

            output_schema_override = None
            expect = case.get("expect", {}) or {}
            if isinstance(expect, dict):
                output_schema_override = expect.get("output_schema")
                checks = expect.get("checks") or []
            else:
                checks = []

            if isinstance(output_schema_override, str):
                schema_path = Path(output_schema_override)
                if not schema_path.is_absolute():
                    schema_path = (test_path.parent / schema_path).resolve()
                output_schema_override = str(schema_path)

            output_valid, output_payload, output_errors = _validate_output_schema(
                agent, manifest_path, result.last_response, override_schema=output_schema_override
            )
            if output_errors:
                raise LoadError("; ".join(output_errors))

            if checks:
                check_errors = _apply_checks(output_payload if output_payload is not None else {}, checks)
                if check_errors:
                    raise LoadError("; ".join(check_errors))

        except (LoadError, SchemaValidationError) as e:
            status = "fail"
            message = str(e)
        except Exception as e:  # pragma: no cover - defensive
            status = "fail"
            message = str(e)

        results.append(
            {
                "name": case_name,
                "status": status,
                "message": message,
            }
        )
        if status != "pass":
            any_fail = True

    if json_output:
        typer.echo(json.dumps(results, indent=2))
    else:
        table = Table(title="Atomic Tests", border_style="cyan")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Message", style="white")
        for res in results:
            style = "green" if res["status"] == "pass" else "red"
            table.add_row(res["name"], f"[{style}]{res['status']}[/{style}]", res.get("message", ""))
        console.print(table)

    if any_fail:
        raise typer.Exit(EX_RUNTIME)

    raise typer.Exit(EX_OK)


def _write_if_missing(path: Path, content: str, force: bool) -> None:
    """Write content to path if allowed."""
    if path.exists() and not force:
        raise LoadError(f"File already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@atomic_app.command("init")
def init_atomic(
    name: str,
    domain: str | None = typer.Option(None, "--domain", help="Optional domain label"),
    capability: str | None = typer.Option(None, "--capability", help="Optional capability label"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Scaffold a new atomic agent manifest, schemas, and tests."""
    root = Path.cwd()
    agent_dir = root / "agents" / "atomic" / name
    manifest_path = agent_dir / f"{name}.yaml"
    input_schema_path = agent_dir / "schemas" / "input.json"
    output_schema_path = agent_dir / "schemas" / "output.json"
    tests_path = agent_dir / "tests.yaml"
    example_input_path = agent_dir / "examples" / "sample.json"

    manifest = f"""version: 0
name: {name}
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  {name}:
    prompt: |
      You are a focused agent that performs {capability or 'a single task'}.
    input_schema: ./schemas/input.json
    output_schema: ./schemas/output.json
metadata:
  labels:
    strands.io/agent_type: atomic
    strands.io/version: v1
"""
    if domain:
        manifest += f"    strands.io/domain: {domain}\n"
    if capability:
        manifest += f"    strands.io/capability: {capability}\n"

    manifest += """pattern:
  type: chain
  config:
    steps:
      - agent: %s
        input: |
          Provide a response for the given input:
          {{ inputs.values | default({}, true) | tojson }}
        tool_overrides: []
""" % name

    input_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"topic": {"type": "string", "description": "Topic to analyze"}},
        "required": ["topic"],
    }

    output_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"summary": {"type": "string"}, "notes": {"type": "array", "items": {"type": "string"}}},
        "required": ["summary"],
    }

    tests_content = f"""tests:
  - name: sample
    input: ./examples/sample.json
    expect:
      output_schema: ./schemas/output.json
      checks:
        - type: has_keys
          keys: ["summary"]
"""

    example_input = {"topic": f"Sample topic for {name}"}

    try:
        _write_if_missing(manifest_path, manifest, force)
        _write_if_missing(input_schema_path, json.dumps(input_schema, indent=2), force)
        _write_if_missing(output_schema_path, json.dumps(output_schema, indent=2), force)
        _write_if_missing(tests_path, tests_content, force)
        _write_if_missing(example_input_path, json.dumps(example_input, indent=2), force)
    except LoadError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(EX_IO)

    console.print("[green]Atomic scaffold created[/green]")
    console.print(f"  [cyan]{manifest_path}")
    console.print(f"  [cyan]{input_schema_path}")
    console.print(f"  [cyan]{output_schema_path}")
    console.print(f"  [cyan]{tests_path}")
    console.print(f"  [cyan]{example_input_path}")


@atomic_app.command("validate")
def validate_atomic(path_or_name: str) -> None:
    """Validate atomic manifest invariants and contract references."""
    manifest_path = _resolve_manifest(path_or_name)

    try:
        spec = load_spec(str(manifest_path))
    except LoadError as e:
        console.print(f"[red]Failed to load spec: {e}[/red]")
        raise typer.Exit(EX_IO)
    except SchemaValidationError as e:
        console.print(f"[red]Schema validation failed: {e}[/red]")
        raise typer.Exit(EX_SCHEMA)

    invariant_errors = check_atomic_invariants(spec)
    contract_errors = _validate_contract_files(spec, manifest_path)

    if invariant_errors or contract_errors:
        console.print("[red]Atomic validation failed[/red]")
        for err in invariant_errors + contract_errors:
            console.print(f"  - {err}")
        raise typer.Exit(EX_USAGE)

    console.print("[green]Atomic manifest is valid[/green]")
