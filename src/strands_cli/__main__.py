"""Main entry point for the Strands CLI.

This module provides the Typer-based command-line interface for executing
agentic workflows on AWS Bedrock and Ollama. It handles workflow loading,
schema validation, capability checking, and single-agent execution with
observability scaffolding.

Commands:
    run: Execute a single-agent workflow from YAML/JSON spec
    validate: Validate a spec against JSON Schema
    plan: Show execution plan for a workflow
    explain: Show unsupported features and migration hints
    list-supported: Display supported feature set
    version: Show CLI version

Key Design:
    - Parse full multi-agent schema but gracefully reject unsupported features
    - Exit with structured error codes for different failure modes
    - Generate actionable remediation reports for unsupported specs
"""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strands_cli import __version__
from strands_cli.artifacts import ArtifactError, write_artifacts
from strands_cli.capability import check_capability, generate_markdown_report
from strands_cli.exec.chain import ChainExecutionError, run_chain

# Import executors
from strands_cli.exec.routing import RoutingExecutionError, run_routing
from strands_cli.exec.single_agent import ExecutionError as SingleAgentExecutionError
from strands_cli.exec.single_agent import run_single_agent
from strands_cli.exec.workflow import WorkflowExecutionError, run_workflow
from strands_cli.exit_codes import (
    EX_IO,
    EX_OK,
    EX_RUNTIME,
    EX_SCHEMA,
    EX_UNKNOWN,
    EX_UNSUPPORTED,
)
from strands_cli.loader import LoadError, load_spec, parse_variables
from strands_cli.schema import SchemaValidationError
from strands_cli.telemetry import configure_telemetry
from strands_cli.types import PatternType

# Combine execution errors for exception handling
ExecutionError = (
    SingleAgentExecutionError,
    ChainExecutionError,
    WorkflowExecutionError,
    RoutingExecutionError,
)

app = typer.Typer(
    name="strands",
    help="Execute agentic workflows on AWS Bedrock/Ollama with observability",
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()


@app.command()
def version() -> None:
    """Show the version of strands-cli.

    Prints the current version to stdout for scripting and debugging.
    """
    console.print(f"strands-cli version {__version__}")


@app.command()
def run(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    var: Annotated[
        list[str] | None, typer.Option("--var", help="Variable override (key=value)")
    ] = None,
    out: Annotated[
        str, typer.Option("--out", help="Output directory for artifacts")
    ] = "./artifacts",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing artifacts")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Run a single-agent workflow from a YAML or JSON file.

    Execution flow:
        1. Load and validate spec against JSON Schema
        2. Check capability compatibility (single agent, supported patterns)
        3. If unsupported features detected, generate remediation report and exit
        4. Build Strands Agent with configured tools and model
        5. Execute workflow with retry logic for transient errors
        6. Write output artifacts using template rendering

    Args:
        spec_file: Path to workflow specification file (.yaml, .yml, or .json)
        var: CLI variable overrides in key=value format, merged into inputs.values
        out: Output directory for artifacts (default: ./artifacts)
        force: Overwrite existing artifact files without error
        verbose: Enable detailed logging and error traces

    Exit Codes:
        EX_OK (0): Successful execution
        EX_SCHEMA (3): Schema validation failed
        EX_RUNTIME (10): Provider/model/tool runtime error
        EX_IO (12): Artifact write failure
        EX_UNSUPPORTED (18): Unsupported features detected (report written)
        EX_UNKNOWN (70): Unexpected exception
    """
    try:
        # Parse variables
        variables = parse_variables(var) if var else {}

        if verbose:
            console.print(f"[dim]Loading spec: {spec_file}[/dim]")
            if variables:
                console.print(f"[dim]Variables: {variables}[/dim]")

        # Load and validate spec
        try:
            spec = load_spec(spec_file, variables)
        except (LoadError, SchemaValidationError) as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(EX_SCHEMA)

        # Check capability compatibility for single-agent execution
        # This validates that the spec uses only supported features (1 agent, chain/workflow pattern, etc.)
        capability_report = check_capability(spec)

        if not capability_report.supported:
            # Generate unsupported features report
            spec_content = Path(spec_file).read_text(encoding="utf-8")
            report_md = generate_markdown_report(spec_file, spec_content, capability_report)

            # Write report to artifacts
            report_path = Path(out) / f"{spec.name}-unsupported.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report_md, encoding="utf-8")

            console.print("\n[yellow]Unsupported features detected.[/yellow]")
            console.print(f"Report written to: [cyan]{report_path}[/cyan]\n")

            # Show summary
            for issue in capability_report.issues[:3]:
                console.print(f"  • {issue.reason}")
                console.print(f"    [dim]→ {issue.remediation}[/dim]\n")

            if len(capability_report.issues) > 3:
                console.print(
                    f"  [dim]... and {len(capability_report.issues) - 3} more issue(s)[/dim]\n"
                )

            sys.exit(EX_UNSUPPORTED)

        # Configure telemetry (currently scaffolding only - config is parsed but no spans are emitted)
        if spec.telemetry:
            configure_telemetry(spec.telemetry.model_dump() if spec.telemetry else None)

        # Execute the workflow
        console.print(f"[bold green]Running workflow:[/bold green] {spec.name}")
        if verbose:
            console.print(f"[dim]Provider: {spec.runtime.provider}[/dim]")
            console.print(f"[dim]Model: {spec.runtime.model_id or 'default'}[/dim]")
            console.print(f"[dim]Pattern: {spec.pattern.type}[/dim]")

        try:
            # Route to appropriate executor based on pattern type
            if spec.pattern.type == PatternType.CHAIN:
                if spec.pattern.config.steps and len(spec.pattern.config.steps) == 1:
                    # Single-step chain - use legacy executor for backward compatibility
                    result = run_single_agent(spec, variables)
                else:
                    # Multi-step chain - use new chain executor
                    result = run_chain(spec, variables)
            elif spec.pattern.type == PatternType.WORKFLOW:
                if spec.pattern.config.tasks and len(spec.pattern.config.tasks) == 1:
                    # Single-task workflow - use legacy executor for backward compatibility
                    result = run_single_agent(spec, variables)
                else:
                    # Multi-task workflow - use new workflow executor
                    result = run_workflow(spec, variables)
            elif spec.pattern.type == PatternType.ROUTING:
                # Routing pattern - use routing executor
                result = run_routing(spec, variables)
            else:
                # Other patterns (parallel, etc.) - not yet supported
                console.print(
                    f"\n[red]Error:[/red] Pattern '{spec.pattern.type}' not supported yet"
                )
                sys.exit(EX_UNSUPPORTED)

        except ExecutionError as e:
            console.print(f"\n[red]Execution failed:[/red] {e}")
            sys.exit(EX_RUNTIME)

        if not result.success:
            console.print(f"\n[red]Workflow failed:[/red] {result.error}")
            sys.exit(EX_RUNTIME)

        # Write artifacts
        if spec.outputs and spec.outputs.artifacts:
            try:
                written_files = write_artifacts(
                    spec.outputs.artifacts,
                    result.last_response or "",
                    out,
                    force,
                    variables=variables,
                    execution_context=result.execution_context,
                )
                result.artifacts_written = written_files
            except ArtifactError as e:
                console.print(f"\n[red]Failed to write artifacts:[/red] {e}")
                sys.exit(EX_IO)

        # Show success summary
        console.print("\n[bold green]✓ Workflow completed successfully[/bold green]")
        console.print(f"Duration: {result.duration_seconds:.2f}s")

        if result.artifacts_written:
            console.print("\nArtifacts written:")
            for artifact in result.artifacts_written:
                console.print(f"  • [cyan]{artifact}[/cyan]")

        sys.exit(EX_OK)

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(EX_UNKNOWN)


@app.command()
def validate(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Validate a workflow spec against the JSON Schema.

    Performs JSON Schema Draft 2020-12 validation and Pydantic model conversion.
    Does not check capability compatibility (use 'plan' or 'explain' for that).

    Args:
        spec_file: Path to workflow specification file
        verbose: Enable verbose output with validation details

    Exit Codes:
        EX_OK (0): Validation successful
        EX_SCHEMA (3): Schema validation or parsing failed
        EX_UNKNOWN (70): Unexpected error
    """
    try:
        if verbose:
            console.print(f"[dim]Validating: {spec_file}[/dim]")

        try:
            spec = load_spec(spec_file)
        except (LoadError, SchemaValidationError) as e:
            console.print(f"[red]Validation failed:[/red]\n{e}")
            sys.exit(EX_SCHEMA)

        console.print(f"[green]OK Spec is valid:[/green] {spec.name}")
        console.print(f"  Version: {spec.version}")
        console.print(f"  Agents: {len(spec.agents)}")
        console.print(f"  Pattern: {spec.pattern.type}")

        sys.exit(EX_OK)

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(EX_UNKNOWN)


@app.command()
def plan(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    format: Annotated[str, typer.Option("--format", help="Output format (md or json)")] = "md",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Show execution plan for a workflow (agents, tools, pattern).

    Displays runtime configuration, agent details, pattern type, and capability
    compatibility status. Useful for previewing workflow execution without running it.

    Args:
        spec_file: Path to workflow specification file
        format: Output format - 'md' for human-readable Markdown (default) or 'json' for structured data
        verbose: Enable verbose output with additional details

    Exit Codes:
        EX_OK (0): Plan generated successfully
        EX_SCHEMA (3): Schema validation failed
        EX_UNKNOWN (70): Unexpected error
    """
    try:
        if verbose:
            console.print(f"[dim]Planning: {spec_file}[/dim]")

        try:
            spec = load_spec(spec_file)
        except (LoadError, SchemaValidationError) as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(EX_SCHEMA)

        # Check capability
        capability_report = check_capability(spec)

        if format == "json":
            import json

            plan_data = {
                "name": spec.name,
                "version": spec.version,
                "supported": capability_report.supported,
                "runtime": {
                    "provider": spec.runtime.provider,
                    "model_id": spec.runtime.model_id,
                    "region": spec.runtime.region,
                    "host": spec.runtime.host,
                },
                "agents": list(spec.agents.keys()),
                "pattern": spec.pattern.type,
                "issues": len(capability_report.issues),
            }
            console.print(json.dumps(plan_data, indent=2))
        else:
            # Markdown format
            console.print(Panel(f"[bold]{spec.name}[/bold]", title="Workflow Plan"))

            # Runtime table
            runtime_table = Table(title="Runtime Configuration")
            runtime_table.add_column("Setting", style="cyan")
            runtime_table.add_column("Value", style="green")
            runtime_table.add_row("Provider", spec.runtime.provider)
            runtime_table.add_row("Model", spec.runtime.model_id or "default")
            if spec.runtime.region:
                runtime_table.add_row("Region", spec.runtime.region)
            if spec.runtime.host:
                runtime_table.add_row("Host", spec.runtime.host)
            console.print(runtime_table)

            # Agents table
            agents_table = Table(title="Agents")
            agents_table.add_column("ID", style="cyan")
            agents_table.add_column("Tools", style="yellow")
            for agent_id, agent in spec.agents.items():
                tools_str = str(len(agent.tools)) if agent.tools else "0"
                agents_table.add_row(agent_id, tools_str)
            console.print(agents_table)

            # Pattern info
            console.print(f"\n[bold]Pattern:[/bold] {spec.pattern.type}")

            # Capability status
            if capability_report.supported:
                console.print("\n[green]✓ MVP Compatible[/green]")
            else:
                console.print(
                    f"\n[yellow]⚠ Unsupported Features:[/yellow] {len(capability_report.issues)}"
                )
                for issue in capability_report.issues[:3]:
                    console.print(f"  • {issue.reason}")
                if len(capability_report.issues) > 3:
                    console.print(f"  [dim]... and {len(capability_report.issues) - 3} more[/dim]")

        sys.exit(EX_OK)

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(EX_UNKNOWN)


@app.command()
def explain(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Explain unsupported features and show migration hints.

    Analyzes a workflow spec for capability compatibility and displays detailed
    remediation guidance for any unsupported features. Each issue includes the
    JSONPointer location, reason, and specific fix instructions.

    Args:
        spec_file: Path to workflow specification file
        verbose: Enable verbose output

    Exit Codes:
        EX_OK (0): Analysis complete (supported or unsupported)
        EX_SCHEMA (3): Schema validation failed
        EX_UNKNOWN (70): Unexpected error
    """
    try:
        if verbose:
            console.print(f"[dim]Analyzing: {spec_file}[/dim]")

        try:
            spec = load_spec(spec_file)
        except (LoadError, SchemaValidationError) as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(EX_SCHEMA)

        # Check capability
        capability_report = check_capability(spec)

        if capability_report.supported:
            console.print("[green]✓ No unsupported features detected.[/green]")
            console.print("This workflow is compatible with the current MVP.")
            sys.exit(EX_OK)

        # Show unsupported features
        console.print(f"\n[yellow]Unsupported Features in {spec.name}:[/yellow]\n")

        for i, issue in enumerate(capability_report.issues, 1):
            console.print(f"[bold]{i}. {issue.pointer}[/bold]")
            console.print(f"   Reason: {issue.reason}")
            console.print(f"   [green]→ Remediation:[/green] {issue.remediation}\n")

        console.print("[dim]Run `strands plan <spec>` to see the full execution plan.[/dim]")
        console.print("[dim]Run `strands list-supported` to see all MVP features.[/dim]")

        sys.exit(EX_OK)

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(EX_UNKNOWN)


@app.command()
def list_supported() -> None:
    """Show the supported feature set.

    Displays a comprehensive table of currently supported workflow features,
    including agent limits, pattern types, providers, tools, and configuration options.
    """
    console.print(Panel("[bold]Strands CLI Phase 1 — Supported Features[/bold]", style="green"))

    features = [
        ("Agents", "Exactly 1 agent"),
        ("Patterns", "chain (multi-step) OR workflow (multi-task DAG)"),
        ("Providers", "bedrock, ollama"),
        ("Python Tools", "strands_tools.http_request, strands_tools.file_read"),
        ("HTTP Executors", "Full support"),
        ("Secrets", "source: env only"),
        ("Skills", "Metadata injection (no code exec)"),
        ("Budgets", "Tracked with 80% warning threshold"),
        ("Retries", "Exponential backoff for transient errors"),
        ("Artifacts", "{{ last_response }}, {{ steps[n].response }}, {{ tasks.<id>.response }}"),
        ("Context", "Explicit step/task references in templates"),
        ("OTEL", "Parsed (no-op; scaffolding ready)"),
    ]

    table = Table(title="Phase 1 Features (v0.2.0)")
    table.add_column("Feature", style="cyan", no_wrap=True)
    table.add_column("Support", style="green")

    for feature, support in features:
        table.add_row(feature, support)

    console.print(table)

    console.print("\n[dim]For the full schema and roadmap, see:[/dim]")
    console.print("[dim]  docs/strands-workflow.schema.json[/dim]")
    console.print("[dim]  PLAN.md - Multi-agent roadmap[/dim]")

    sys.exit(EX_OK)


@app.command()
def doctor() -> None:
    """Run diagnostic checks on strands-cli installation.

    Verifies that the CLI environment is properly configured:
    - Python version (>= 3.12)
    - Schema file exists
    - Ollama server connectivity (if configured)
    - Core dependencies installed

    Use this command to troubleshoot installation or connectivity issues.
    """
    console.print(Panel.fit("[bold]Strands CLI Health Check[/bold]", border_style="cyan"))
    console.print()

    checks_passed = 0
    checks_failed = 0

    # Check 1: Python version
    console.print("[cyan]→[/cyan] Checking Python version...")
    import sys as pysys

    python_version = (
        f"{pysys.version_info.major}.{pysys.version_info.minor}.{pysys.version_info.micro}"
    )

    if pysys.version_info >= (3, 12):
        console.print(f"  [green]✓[/green] Python {python_version} (>= 3.12 required)")
        checks_passed += 1
    else:
        console.print(f"  [red]✗[/red] Python {python_version} (>= 3.12 required)")
        checks_failed += 1

    # Check 2: Schema file exists
    console.print("\n[cyan]→[/cyan] Checking schema file...")
    from pathlib import Path

    schema_path = Path(__file__).parent.parent.parent / "docs" / "strands-workflow.schema.json"

    if schema_path.exists():
        console.print(f"  [green]✓[/green] Schema file found: {schema_path}")
        checks_passed += 1
    else:
        console.print(f"  [red]✗[/red] Schema file not found: {schema_path}")
        console.print("      [yellow]Try reinstalling with:[/yellow] uv sync")
        checks_failed += 1

    # Check 3: Core dependencies
    console.print("\n[cyan]→[/cyan] Checking core dependencies...")
    required_modules = ["typer", "pydantic", "ruamel.yaml", "strands.agent", "structlog"]
    missing_modules = []

    for module_name in required_modules:
        try:
            __import__(module_name.replace(".agent", ".agent"))  # Handle strands.agent
            console.print(f"  [green]✓[/green] {module_name}")
        except ImportError:
            console.print(f"  [red]✗[/red] {module_name} (not installed)")
            missing_modules.append(module_name)
            checks_failed += 1

    if not missing_modules:
        checks_passed += 1

    # Check 4: Ollama connectivity (optional)
    console.print("\n[cyan]→[/cyan] Checking Ollama server connectivity...")
    try:
        import httpx

        response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if response.status_code == 200:
            console.print("  [green]✓[/green] Ollama server is running at http://localhost:11434")
            checks_passed += 1
        else:
            console.print(
                f"  [yellow]![/yellow] Ollama server responded with status {response.status_code}"
            )
            console.print("      [dim]This is optional if using Bedrock only[/dim]")
    except Exception as e:
        console.print(f"  [yellow]![/yellow] Ollama server not reachable: {type(e).__name__}")
        console.print("      [dim]This is optional if using Bedrock only[/dim]")
        console.print("      [dim]Install Ollama: https://ollama.ai[/dim]")

    # Summary
    console.print()
    console.print("[bold]Summary:[/bold]")
    total_required = 3  # Python, schema, dependencies (Ollama is optional)

    if checks_failed == 0:
        console.print(f"  [green]✓ All {total_required} required checks passed![/green]")
        console.print("\n[dim]strands-cli is ready to use.[/dim]")
        sys.exit(EX_OK)
    else:
        console.print(f"  [red]✗ {checks_failed} check(s) failed[/red]")
        console.print(f"  [green]✓ {checks_passed} check(s) passed[/green]")
        console.print("\n[yellow]Please fix the issues above before running workflows.[/yellow]")
        sys.exit(EX_RUNTIME)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
