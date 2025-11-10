"""Main entry point for the Strands CLI.

This module provides the Typer-based command-line interface for executing
agentic workflows on AWS Bedrock and Ollama. It handles workflow loading,
schema validation, capability checking, and workflow execution with
observability scaffolding.

Phase 3-6 Performance Updates:
    - All executors now async (single-agent, chain, workflow, parallel, routing)
    - Single event loop per workflow execution (eliminates per-step loop churn)
    - AgentCache shared across all steps/tasks/branches for agent reuse
    - HTTP clients properly cleaned up after execution

Commands:
    run: Execute a workflow from YAML/JSON spec
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

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import structlog
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strands_cli import __version__
from strands_cli.artifacts import ArtifactError, write_artifacts
from strands_cli.capability import (
    CapabilityReport,
    check_capability,
    generate_markdown_report,
)
from strands_cli.config import StrandsConfig
from strands_cli.exec.chain import ChainExecutionError, run_chain

# Import executors
from strands_cli.exec.evaluator_optimizer import (
    EvaluatorOptimizerExecutionError,
    run_evaluator_optimizer,
)
from strands_cli.exec.parallel import ParallelExecutionError, run_parallel
from strands_cli.exec.routing import RoutingExecutionError, run_routing
from strands_cli.exec.single_agent import ExecutionError as SingleAgentExecutionError
from strands_cli.exec.single_agent import run_single_agent
from strands_cli.exec.workflow import WorkflowExecutionError, run_workflow
from strands_cli.exit_codes import (
    EX_HITL_PAUSE,
    EX_IO,
    EX_OK,
    EX_RUNTIME,
    EX_SCHEMA,
    EX_SESSION,
    EX_UNKNOWN,
    EX_UNSUPPORTED,
    EX_USAGE,
)
from strands_cli.loader import LoadError, load_spec, parse_variables
from strands_cli.schema import SchemaValidationError
from strands_cli.session import (
    SessionAlreadyCompletedError,
    SessionError,
    SessionNotFoundError,
    SessionState,
)
from strands_cli.session.file_repository import FileSessionRepository
from strands_cli.telemetry import add_otel_context, configure_telemetry, shutdown_telemetry
from strands_cli.types import PatternType, RunResult, Spec

# Load config to determine log format
config = StrandsConfig()

# Determine log level (INFO by default, DEBUG when STRANDS_DEBUG=true)
log_level_str = os.environ.get("STRANDS_DEBUG", "").lower()
min_level = logging.DEBUG if log_level_str == "true" else logging.INFO


def _spec_has_hitl_steps(spec: Spec) -> bool:
    """Check if spec contains any HITL steps.

    Currently only checks chain pattern. Future: Add workflow, parallel, etc.

    Args:
        spec: Workflow specification

    Returns:
        True if spec contains HITL steps, False otherwise
    """
    if spec.pattern.type == PatternType.CHAIN:
        steps = spec.pattern.config.steps
        if steps is None:
            return False
        return any(hasattr(step, "type") and step.type == "hitl" for step in steps)
    # TODO: Add HITL detection for other patterns when they support HITL
    # - workflow pattern (tasks with type=hitl)
    # - parallel pattern (branches with HITL steps)
    return False


# Custom log level filter processor for structlog
def filter_by_level_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Filter log events by level."""
    level_name = event_dict.get("level", "info").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    event_level = level_map.get(level_name, logging.INFO)
    if event_level < min_level:
        raise structlog.DropEvent
    return event_dict


# Configure structlog with OTEL context injection
# Use ConsoleRenderer for user-friendly output by default, JSONRenderer for debug/telemetry
renderer = (
    structlog.processors.JSONRenderer()
    if config.log_format == "json"
    else structlog.dev.ConsoleRenderer(colors=True)
)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        filter_by_level_processor,  # type: ignore[list-item]
        add_otel_context,  # type: ignore[list-item]
        renderer,
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# Combine execution errors for exception handling
ExecutionError = (
    SingleAgentExecutionError,
    ChainExecutionError,
    WorkflowExecutionError,
    RoutingExecutionError,
    ParallelExecutionError,
    EvaluatorOptimizerExecutionError,
)

app = typer.Typer(
    name="strands",
    help="Execute agentic workflows on AWS Bedrock/Ollama with observability",
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()


# Helper functions for run command (extracted to reduce cyclomatic complexity)


def _load_and_validate_spec(
    spec_file: str,
    variables: dict[str, str] | None,
    verbose: bool,
) -> tuple[Spec, Path]:
    """Load and validate spec with error handling.

    Args:
        spec_file: Path to workflow specification file
        variables: Variable overrides from --var flags
        verbose: Enable verbose output

    Returns:
        Tuple of (validated Spec object, Path to spec file)

    Raises:
        SystemExit: With EX_SCHEMA on validation error
    """
    if verbose:
        console.print(f"[dim]Loading spec: {spec_file}[/dim]")
        if variables:
            console.print(f"[dim]Variables: {variables}[/dim]")

    try:
        spec = load_spec(spec_file, variables)
        spec_path = Path(spec_file)
        return spec, spec_path
    except (LoadError, SchemaValidationError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(EX_SCHEMA)


def _handle_unsupported_spec(
    spec: Spec,
    spec_path: Path,
    capability_report: CapabilityReport,
    out: str,
) -> None:
    """Generate and display unsupported features report, then exit.

    Args:
        spec: Loaded workflow spec
        spec_path: Path to spec file
        capability_report: Capability check results
        out: Output directory for reports

    Raises:
        SystemExit: With EX_UNSUPPORTED (18)
    """
    from strands_cli.artifacts import sanitize_filename

    # Generate report
    spec_content = spec_path.read_text(encoding="utf-8")
    report_md = generate_markdown_report(str(spec_path), spec_content, capability_report)

    # Sanitize spec name for filesystem (prevents path traversal)
    safe_name = sanitize_filename(spec.name)
    report_path = Path(out) / f"{safe_name}-unsupported.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")

    console.print("\n[yellow]Unsupported features detected.[/yellow]")
    console.print(f"Report written to: [cyan]{report_path}[/cyan]\n")

    # Show summary
    for issue in capability_report.issues[:3]:
        console.print(f"  • {issue.reason}")
        console.print(f"    [dim]→ {issue.remediation}[/dim]\n")

    if len(capability_report.issues) > 3:
        console.print(f"  [dim]... and {len(capability_report.issues) - 3} more issue(s)[/dim]\n")

    sys.exit(EX_UNSUPPORTED)


def _route_to_executor(
    spec: Spec,
    variables: dict[str, str] | None,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
) -> RunResult:
    """Route to appropriate executor based on pattern type.

    Phase 3: Single-agent executor is now async; wraps with asyncio.run()
    to maintain single event loop per workflow execution.

    Args:
        spec: Validated workflow spec
        variables: Variable overrides from --var flags
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)

    Returns:
        RunResult from the appropriate executor

    Raises:
        SystemExit: With EX_UNSUPPORTED for unknown patterns
    """
    if spec.pattern.type == PatternType.CHAIN:
        if spec.pattern.config.steps and len(spec.pattern.config.steps) == 1:
            # Single-step chain - use async single-agent executor
            # Phase 3: Wrap with asyncio.run() for single event loop
            return asyncio.run(run_single_agent(spec, variables, session_state, session_repo))
        else:
            # Multi-step chain - use async chain executor
            # Phase 4: Wrap with asyncio.run() for single event loop
            return asyncio.run(run_chain(spec, variables, session_state, session_repo))
    elif spec.pattern.type == PatternType.WORKFLOW:
        if spec.pattern.config.tasks and len(spec.pattern.config.tasks) == 1:
            # Single-task workflow - use async single-agent executor
            # Phase 3: Wrap with asyncio.run() for single event loop
            return asyncio.run(run_single_agent(spec, variables, session_state, session_repo))
        else:
            # Multi-task workflow - use async workflow executor
            # Phase 5: Wrap with asyncio.run() for single event loop
            return asyncio.run(run_workflow(spec, variables, session_state, session_repo))
    elif spec.pattern.type == PatternType.ROUTING:
        # Routing pattern - use async routing executor
        # Phase 6: Wrap with asyncio.run() for single event loop
        return asyncio.run(run_routing(spec, variables, session_state, session_repo))
    elif spec.pattern.type == PatternType.PARALLEL:
        # Parallel pattern - use async parallel executor
        # Phase 6: Wrap with asyncio.run() for single event loop
        return asyncio.run(run_parallel(spec, variables, session_state, session_repo))
    elif spec.pattern.type == PatternType.EVALUATOR_OPTIMIZER:
        # Evaluator-optimizer pattern - use async evaluator-optimizer executor
        # Phase 4: Wrap with asyncio.run() for single event loop
        return asyncio.run(run_evaluator_optimizer(spec, variables, session_state, session_repo))
    elif spec.pattern.type == PatternType.ORCHESTRATOR_WORKERS:
        # Orchestrator-workers pattern - use async orchestrator-workers executor
        # Phase 7: Wrap with asyncio.run() for single event loop
        from strands_cli.exec.orchestrator_workers import run_orchestrator_workers

        return asyncio.run(run_orchestrator_workers(spec, variables, session_state, session_repo))
    elif spec.pattern.type == PatternType.GRAPH:
        # Graph pattern - use async graph executor
        # Phase 8: Wrap with asyncio.run() for single event loop
        from strands_cli.exec.graph import run_graph

        return asyncio.run(run_graph(spec, variables, session_state, session_repo))
    else:
        # Other patterns - not yet supported
        console.print(f"\n[red]Error:[/red] Pattern '{spec.pattern.type}' not supported yet")
        sys.exit(EX_UNSUPPORTED)


def _dispatch_executor(
    spec: Spec,
    variables: dict[str, str] | None,
    verbose: bool,
    session_state: SessionState | None = None,
    session_repo: FileSessionRepository | None = None,
) -> RunResult:
    """Route to appropriate executor based on pattern type.

    Args:
        spec: Validated workflow spec
        variables: Variable overrides from --var flags
        verbose: Enable verbose output
        session_state: Existing session state for resume (None = fresh start)
        session_repo: Repository for checkpointing (None = no checkpoints)

    Returns:
        RunResult from the appropriate executor

    Raises:
        SystemExit: With EX_RUNTIME on execution error or EX_UNSUPPORTED for unknown patterns
    """
    console.print(f"[bold green]Running workflow:[/bold green] {spec.name}")
    if verbose:
        console.print(f"[dim]Provider: {spec.runtime.provider}[/dim]")
        console.print(f"[dim]Model: {spec.runtime.model_id or 'default'}[/dim]")
        console.print(f"[dim]Pattern: {spec.pattern.type}[/dim]")

    try:
        return _route_to_executor(spec, variables, session_state, session_repo)
    except ExecutionError as e:
        console.print(f"\n[red]Execution failed:[/red] {e}")
        if verbose:
            console.print_exception()
        sys.exit(EX_RUNTIME)
    except (
        ChainExecutionError,
        WorkflowExecutionError,
        RoutingExecutionError,
        ParallelExecutionError,
    ) as e:
        console.print(f"\n[red]Execution failed:[/red] {e}")
        if verbose:
            console.print_exception()
        sys.exit(EX_RUNTIME)
    except Exception as e:
        # Phase 6.4: Handle budget exceeded error
        from strands_cli.runtime.budget_enforcer import BudgetExceededError

        if isinstance(e, BudgetExceededError):
            console.print(f"\n[red]Budget exceeded:[/red] {e}")
            if verbose:
                console.print(f"[dim]Tokens used: {e.cumulative_tokens}/{e.max_tokens}[/dim]")
            sys.exit(e.exit_code)

        # Re-raise other exceptions
        raise


def _write_and_report_artifacts(
    spec: Spec,
    result: RunResult,
    out: str,
    force: bool,
    variables: dict[str, str] | None,
) -> list[str]:
    """Write artifacts and handle errors.

    Args:
        spec: Workflow spec
        result: Execution result with last_response
        out: Output directory
        force: Overwrite existing files
        variables: Template variables from --var flags

    Returns:
        List of written artifact paths

    Raises:
        SystemExit: With EX_IO on write failure
    """
    if not spec.outputs or not spec.outputs.artifacts:
        return []

    try:
        # Extract merged variables from spec.inputs.values (includes YAML defaults + CLI overrides)
        merged_vars: dict[str, Any] = {}
        if spec.inputs and isinstance(spec.inputs, dict) and "values" in spec.inputs:
            merged_vars = dict(spec.inputs["values"] or {})
        # Overlay CLI --var overrides (takes precedence over spec defaults)
        if variables:
            merged_vars.update(variables)

        return write_artifacts(
            spec.outputs.artifacts,
            result.last_response or "",
            out,
            force,
            variables=merged_vars,
            execution_context=result.execution_context,
            spec_name=spec.name,
            pattern_type=spec.pattern.type if spec.pattern else None,
        )
    except ArtifactError as e:
        console.print(f"\n[red]Failed to write artifacts:[/red] {e}")
        sys.exit(EX_IO)


def _write_trace_artifact(spec: Spec, out: str, force: bool) -> str | None:
    """Write trace artifact to JSON file.

    Args:
        spec: Workflow spec
        out: Output directory
        force: Overwrite existing files

    Returns:
        Path to written trace file, or None if no trace collector

    Raises:
        SystemExit: With EX_IO on write failure
    """
    from strands_cli.artifacts import sanitize_filename
    from strands_cli.telemetry import force_flush_telemetry, get_trace_collector

    collector = get_trace_collector()
    if not collector:
        console.print(
            "[yellow]Warning:[/yellow] No trace data available (telemetry not configured)"
        )
        return None

    try:
        # Phase 10: Force flush pending spans before collecting trace data
        # BatchSpanProcessor exports on background thread, so we need to flush
        # to ensure all spans are exported before we read the collector
        flush_success = force_flush_telemetry(timeout_millis=5000)
        if not flush_success:
            console.print(
                "[yellow]⚠ Warning:[/yellow] Trace export timed out. "
                "Artifact may be incomplete. Try increasing timeout or check OTLP endpoint."
            )

        # Get trace data with spec metadata
        trace_data = collector.get_trace_data(
            spec_name=spec.name, pattern=spec.pattern.type if spec.pattern else None
        )

        # Generate safe filename
        safe_name = sanitize_filename(spec.name)
        trace_path = Path(out) / f"{safe_name}-trace.json"

        # Check if file exists
        if trace_path.exists() and not force:
            console.print(
                f"\n[red]Trace file already exists:[/red] {trace_path}. Use --force to overwrite."
            )
            sys.exit(EX_IO)

        # Write trace JSON with pretty formatting
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(trace_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return str(trace_path)

    except Exception as e:
        console.print(f"\n[red]Failed to write trace artifact:[/red] {e}")
        sys.exit(EX_IO)


@app.command()
def version() -> None:
    """Show the version of strands-cli.

    Prints the current version to stdout for scripting and debugging.
    """
    console.print(f"strands-cli version {__version__}")


@app.command()
def run(  # noqa: C901 - Complexity acceptable for main CLI command orchestration
    spec_file: Annotated[
        str | None,
        typer.Argument(help="Path to workflow YAML/JSON file (required unless --resume)"),
    ] = None,
    var: Annotated[
        list[str] | None, typer.Option("--var", help="Variable override (key=value)")
    ] = None,
    out: Annotated[
        str, typer.Option("--out", help="Output directory for artifacts")
    ] = "./artifacts",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing artifacts")] = False,
    bypass_tool_consent: Annotated[
        bool,
        typer.Option(
            "--bypass-tool-consent",
            help="Skip interactive tool confirmations (sets BYPASS_TOOL_CONSENT=true)",
        ),
    ] = False,
    trace: Annotated[
        bool, typer.Option("--trace", help="Generate trace artifact with OTEL spans")
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug logging (variable resolution, templates, etc.)"),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
    resume: Annotated[
        str | None, typer.Option("--resume", "-r", help="Resume from session ID")
    ] = None,
    save_session: Annotated[
        bool,
        typer.Option(
            "--save-session/--no-save-session", help="Save session for resume (default: true)"
        ),
    ] = True,
    auto_resume: Annotated[
        bool,
        typer.Option(
            "--auto-resume",
            help="Auto-resume from most recent failed/paused session if spec matches",
        ),
    ] = False,
    hitl_response: Annotated[
        str | None,
        typer.Option(
            "--hitl-response",
            help="User response when resuming from HITL pause (requires --resume)",
        ),
    ] = None,
) -> None:
    """Run a workflow from a YAML/JSON file or resume from saved session.

    Execution flow (normal):
        1. Load and validate spec against JSON Schema
        2. Check capability compatibility (single agent, supported patterns)
        3. If unsupported features detected, generate remediation report and exit
        4. Build Strands Agent with configured tools and model
        5. Execute workflow with retry logic for transient errors
        6. Write output artifacts using template rendering

    Execution flow (resume):
        1. Load session state from FileSessionRepository
        2. Validate session status (can't resume COMPLETED sessions)
        3. Load spec from snapshot file and verify spec hash
        4. Route to pattern-specific executor with session state
        5. Continue execution from last checkpoint

    Execution flow (auto-resume):
        1. Compute spec hash for provided spec_file
        2. Search for most recent failed/paused session matching spec hash
        3. If match found, automatically resume that session
        4. If no match found, execute normally with new session

    Execution flow (HITL resume):
        1. Resume session with --resume <session-id>
        2. Provide user response with --hitl-response "your response"
        3. Workflow continues from next step after HITL pause

    Args:
        spec_file: Path to workflow specification file (.yaml, .yml, or .json) - required unless --resume
        var: CLI variable overrides in key=value format, merged into inputs.values
        out: Output directory for artifacts (default: ./artifacts)
        force: Overwrite existing artifact files without error
        bypass_tool_consent: Skip interactive tool confirmations (e.g., file_write prompts)
        trace: Auto-generate trace artifact with OTEL spans (writes <spec-name>-trace.json)
        debug: Enable debug logging (variable resolution, templates, etc.)
        verbose: Enable detailed logging and error traces
        resume: Resume from session ID (mutually exclusive with spec_file)
        save_session: Save session for resume capability (default: true)
        auto_resume: Auto-resume from most recent failed/paused session if spec matches
        hitl_response: User response when resuming from HITL pause (requires --resume)

    Exit Codes:
        EX_OK (0): Successful execution
        EX_USAGE (2): Invalid arguments (both spec_file and --resume specified)
        EX_SCHEMA (3): Schema validation failed
        EX_RUNTIME (10): Provider/model/tool runtime error
        EX_IO (12): Artifact write failure
        EX_SESSION (17): Session not found or already completed
        EX_UNSUPPORTED (18): Unsupported features detected (report written)
        EX_HITL_PAUSE (19): Workflow paused for human input
        EX_UNKNOWN (70): Unexpected exception
    """
    import os

    try:
        # Validate mutual exclusivity of spec_file and --resume
        if resume and spec_file:
            console.print("[red]Error:[/red] Cannot specify both spec_file and --resume")
            sys.exit(EX_USAGE)
        if not resume and not spec_file:
            console.print("[red]Error:[/red] Must specify either spec_file or --resume")
            sys.exit(EX_USAGE)

        # Validate --hitl-response requires --resume
        if hitl_response and not resume:
            console.print(
                "[red]Error:[/red] --hitl-response requires --resume <session-id>\n"
                "Use --hitl-response only when resuming from a HITL pause."
            )
            sys.exit(EX_USAGE)

        # Configure debug logging level
        if debug:
            os.environ["STRANDS_DEBUG"] = "true"
            import logging

            logging.basicConfig(level=logging.DEBUG)
            console.print("[dim]Debug logging enabled[/dim]")

        # Set environment variable for tool consent bypass if requested
        if bypass_tool_consent:
            os.environ["BYPASS_TOOL_CONSENT"] = "true"
            if verbose:
                console.print("[dim]BYPASS_TOOL_CONSENT enabled[/dim]")

        # Auto-resume: Check for existing failed/paused session matching spec hash
        if auto_resume and spec_file and not resume:
            from strands_cli.session import SessionStatus
            from strands_cli.session.file_repository import FileSessionRepository
            from strands_cli.session.utils import compute_spec_hash

            repo = FileSessionRepository()
            spec_path = Path(spec_file)

            if spec_path.exists():
                spec_hash = compute_spec_hash(spec_path)
                sessions = asyncio.run(repo.list_sessions())

                # Find matching failed/paused sessions
                matching = [
                    s
                    for s in sessions
                    if s.spec_hash == spec_hash
                    and s.status in (SessionStatus.FAILED, SessionStatus.PAUSED)
                ]

                if matching:
                    # Resume most recent matching session
                    latest = max(matching, key=lambda s: s.updated_at)
                    console.print(
                        f"[yellow]Auto-resume detected:[/yellow] Session {latest.session_id[:12]}... "
                        f"({latest.status.value}, updated {latest.updated_at})"
                    )
                    resume = latest.session_id
                elif verbose:
                    console.print(
                        "[dim]No matching failed/paused sessions found, starting fresh[/dim]"
                    )

        # Branch: Resume mode vs Normal mode
        if resume:
            # Resume mode: load session and continue execution
            from strands_cli.session.resume import run_resume

            try:
                result = asyncio.run(
                    run_resume(
                        session_id=resume,
                        hitl_response=hitl_response,
                        debug=debug,
                        verbose=verbose,
                        trace=trace,
                    )
                )

                if not result.success:
                    console.print(f"\n[red]Resume failed:[/red] {result.error}")
                    sys.exit(EX_RUNTIME)

                # BLOCKER 1 FIX: Check if workflow paused at another HITL step
                if result.agent_id == "hitl":
                    # Workflow paused again at next HITL step - exit with pause code
                    shutdown_telemetry()
                    sys.exit(EX_HITL_PAUSE)

                # Write any remaining artifacts
                if result.spec and result.spec.outputs and result.spec.outputs.artifacts:
                    written_files = _write_and_report_artifacts(
                        result.spec, result, out, force, result.variables
                    )
                    result.artifacts_written.extend(written_files)

                # Generate trace artifact if --trace flag is set
                if trace and result.spec:
                    trace_file = _write_trace_artifact(result.spec, out, force)
                    if trace_file:
                        result.artifacts_written.append(trace_file)

                # Show success summary
                console.print("\n[bold green]✓ Workflow resumed successfully[/bold green]")
                console.print(f"Duration: {result.duration_seconds:.2f}s")

                if result.artifacts_written:
                    console.print("\nArtifacts written:")
                    for artifact in result.artifacts_written:
                        console.print(f"  • [cyan]{artifact}[/cyan]")

                # Shutdown telemetry and flush pending spans
                shutdown_telemetry()
                sys.exit(EX_OK)

            except SessionNotFoundError as e:
                console.print(f"[red]Session not found:[/red] {e}")
                console.print("\n[dim]Use 'strands list-sessions' to see available sessions[/dim]")
                sys.exit(EX_SESSION)
            except SessionAlreadyCompletedError as e:
                console.print(f"[yellow]Session already completed:[/yellow] {e}")
                console.print("\n[dim]Start a new workflow or resume a different session[/dim]")
                sys.exit(EX_SESSION)
            except SessionError as e:
                console.print(f"[red]Session error:[/red] {e}")
                sys.exit(EX_SESSION)
            except Exception as e:
                console.print(f"\n[red]Resume failed:[/red] {e}")
                if verbose:
                    console.print_exception()
                sys.exit(EX_RUNTIME)

        # Normal mode: load spec and execute (with optional session saving)

        # Parse variables
        variables = parse_variables(var) if var else {}

        # Load and validate spec
        spec, spec_path = _load_and_validate_spec(spec_file, variables, verbose)  # type: ignore

        # Check capability compatibility
        capability_report = check_capability(spec)

        if not capability_report.supported:
            _handle_unsupported_spec(spec, spec_path, capability_report, out)

        # BLOCKER 2 FIX: Validate HITL steps require session persistence
        if not save_session and _spec_has_hitl_steps(spec):
            console.print(
                "[red]Error:[/red] Workflow contains HITL (Human-in-the-Loop) steps which require session persistence.\n\n"
                "[yellow]HITL steps pause execution and require resuming with:[/yellow]\n"
                "  strands run --resume <session-id> --hitl-response 'your response'\n\n"
                "[cyan]To fix, choose one:[/cyan]\n"
                "  1. Remove --no-save-session flag (recommended)\n"
                "  2. Remove HITL steps from workflow"
            )
            sys.exit(EX_USAGE)

        # Configure telemetry (currently scaffolding only)
        if spec.telemetry:
            configure_telemetry(spec.telemetry.model_dump() if spec.telemetry else None)

        # Create session if save_session is enabled
        session_id = None
        if save_session:
            from strands_cli.session import SessionMetadata, SessionState, SessionStatus, TokenUsage
            from strands_cli.session.file_repository import FileSessionRepository
            from strands_cli.session.utils import (
                compute_spec_hash,
                generate_session_id,
                now_iso8601,
            )

            session_id = generate_session_id()
            repo = FileSessionRepository()

            # Initialize session state
            session_state = SessionState(
                metadata=SessionMetadata(
                    session_id=session_id,
                    workflow_name=spec.name,
                    spec_hash=compute_spec_hash(spec_path),
                    pattern_type=spec.pattern.type.value,
                    status=SessionStatus.RUNNING,
                    created_at=now_iso8601(),
                    updated_at=now_iso8601(),
                ),
                variables=variables or {},
                runtime_config=spec.runtime.model_dump(),
                pattern_state={},  # Pattern-specific state initialized by executor
                token_usage=TokenUsage(),
            )

            # Save initial state with spec snapshot
            spec_content = spec_path.read_text(encoding="utf-8")
            asyncio.run(repo.save(session_state, spec_content))

            logger.info("session_created", session_id=session_id, spec_name=spec.name)
            if verbose:
                console.print(f"[dim]Session ID: {session_id}[/dim]")
        else:
            session_state = None
            repo = None  # type: ignore[assignment]

        # Execute workflow (with session support if enabled)
        result = _dispatch_executor(spec, variables, verbose, session_state, repo)

        if not result.success:
            console.print(f"\n[red]Workflow failed:[/red] {result.error}")
            sys.exit(EX_RUNTIME)

        # Check for HITL pause (agent_id="hitl" indicates pause, not completion)
        if result.agent_id == "hitl":
            # Shutdown telemetry and exit with HITL_PAUSE code
            shutdown_telemetry()
            sys.exit(EX_HITL_PAUSE)

        # Write artifacts
        written_files = _write_and_report_artifacts(spec, result, out, force, variables)
        result.artifacts_written = written_files

        # Generate trace artifact if --trace flag is set
        if trace:
            trace_file = _write_trace_artifact(spec, out, force)
            if trace_file:
                result.artifacts_written.append(trace_file)

        # Show success summary
        console.print("\n[bold green]✓ Workflow completed successfully[/bold green]")
        console.print(f"Duration: {result.duration_seconds:.2f}s")

        if result.artifacts_written:
            console.print("\nArtifacts written:")
            for artifact in result.artifacts_written:
                console.print(f"  • [cyan]{artifact}[/cyan]")

        # Shutdown telemetry and flush pending spans
        shutdown_telemetry()

        sys.exit(EX_OK)

    except Exception as e:
        # Ensure telemetry shutdown even on error
        shutdown_telemetry()
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(EX_UNKNOWN)


@app.command()
def validate(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug logging (variable resolution, templates, etc.)"),
    ] = False,
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
    import os

    try:
        # Configure debug logging level
        if debug:
            os.environ["STRANDS_DEBUG"] = "true"
            import logging

            logging.basicConfig(level=logging.DEBUG)

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


def _display_plan_json(spec: Spec, capability_report: CapabilityReport) -> None:
    """Display plan in JSON format.

    Args:
        spec: Workflow spec
        capability_report: Capability check results
    """
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


def _display_plan_markdown(spec: Spec, capability_report: CapabilityReport) -> None:
    """Display plan in Markdown format with tables.

    Args:
        spec: Workflow spec
        capability_report: Capability check results
    """
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

    # Graph visualization if graph pattern
    if spec.pattern.type == PatternType.GRAPH:
        from strands_cli.visualization.graph_viz import generate_text_visualization

        console.print("\n[bold]Graph Structure:[/bold]")
        viz = generate_text_visualization(spec)
        console.print(f"[dim]{viz}[/dim]")

    # Capability status
    if capability_report.supported:
        console.print("\n[green]✓ MVP Compatible[/green]")
    else:
        console.print(f"\n[yellow]⚠ Unsupported Features:[/yellow] {len(capability_report.issues)}")
        for issue in capability_report.issues[:3]:
            console.print(f"  • {issue.reason}")
        if len(capability_report.issues) > 3:
            console.print(f"  [dim]... and {len(capability_report.issues) - 3} more[/dim]")


@app.command()
def plan(
    spec_file: Annotated[str, typer.Argument(help="Path to workflow YAML/JSON file")],
    format: Annotated[str, typer.Option("--format", help="Output format (md or json)")] = "md",
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug logging (variable resolution, templates, etc.)"),
    ] = False,
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
    import os

    try:
        # Configure debug logging level
        if debug:
            os.environ["STRANDS_DEBUG"] = "true"
            import logging

            logging.basicConfig(level=logging.DEBUG)

        if verbose:
            console.print(f"[dim]Planning: {spec_file}[/dim]")

        try:
            spec = load_spec(spec_file)
        except (LoadError, SchemaValidationError) as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(EX_SCHEMA)

        # Check capability
        capability_report = check_capability(spec)

        # Display plan in requested format
        if format == "json":
            _display_plan_json(spec, capability_report)
        else:
            _display_plan_markdown(spec, capability_report)

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
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug logging (variable resolution, templates, etc.)"),
    ] = False,
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
    import os

    try:
        # Configure debug logging level
        if debug:
            os.environ["STRANDS_DEBUG"] = "true"
            import logging

            logging.basicConfig(level=logging.DEBUG)

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
    console.print(Panel("[bold]Strands CLI Phase 4 — Supported Features[/bold]", style="green"))

    features = [
        ("Agents", "Multiple agents supported"),
        ("Patterns", "chain, workflow, routing, parallel, evaluator-optimizer"),
        ("Providers", "bedrock, ollama, openai"),
        (
            "Python Tools",
            "strands_tools.{http_request, file_read, file_write, calculator, current_time}.{function}",
        ),
        ("HTTP Executors", "Full support"),
        ("Secrets", "source: env only"),
        ("Skills", "Metadata injection (no code exec)"),
        ("Budgets", "Tracked with 80% warning threshold"),
        ("Retries", "Exponential backoff for transient errors"),
        (
            "Artifacts",
            "{{ last_response }}, {{ steps[n].response }}, {{ tasks.<id>.response }}, {{ branches.<id>.response }}, {{ execution.history }}",
        ),
        ("Context", "Explicit step/task/branch references, execution metadata"),
        ("OTEL", "Parsed (no-op; scaffolding ready)"),
    ]

    table = Table(title="Phase 4 Features (v0.5.0)")
    table.add_column("Feature", style="cyan", no_wrap=True)
    table.add_column("Support", style="green")

    for feature, support in features:
        table.add_row(feature, support)

    console.print(table)

    console.print("\n[dim]For the full schema and roadmap, see:[/dim]")
    console.print("[dim]  src/strands_cli/schema/strands-workflow.schema.json[/dim]")
    console.print("[dim]  PLAN.md - Multi-agent roadmap[/dim]")

    sys.exit(EX_OK)


# Session management sub-commands
sessions_app = typer.Typer(
    name="sessions",
    help="Manage workflow sessions for resume capability",
    add_completion=False,
)
app.add_typer(sessions_app, name="sessions")


@sessions_app.command("list")
def sessions_list(
    status: Annotated[
        str | None,
        typer.Option(help="Filter by status (running|paused|completed|failed)"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """List all saved workflow sessions.

    Displays sessions stored in the local filesystem (~/.strands/sessions/),
    showing key metadata like session ID, workflow name, pattern type, status,
    and last update time.

    Filter by status to find sessions that can be resumed (running/paused)
    or view completed/failed sessions for cleanup.

    Examples:
        strands sessions list
        strands sessions list --status running
        strands sessions list --status completed -v
    """
    from strands_cli.session import SessionStatus
    from strands_cli.session.file_repository import FileSessionRepository

    repo = FileSessionRepository()

    # Load sessions (async call wrapped in asyncio.run)
    sessions = asyncio.run(repo.list_sessions())

    # Filter by status if provided
    if status:
        try:
            status_filter = SessionStatus(status.lower())
            sessions = [s for s in sessions if s.status == status_filter]
        except ValueError:
            console.print(f"[red]Invalid status:[/red] {status}")
            console.print("Valid values: running, paused, completed, failed")
            sys.exit(EX_USAGE)

    if not sessions:
        if status:
            console.print(f"[dim]No sessions found with status '{status}'[/dim]")
        else:
            console.print("[dim]No sessions found[/dim]")
        console.print()
        console.print("[dim]Sessions are saved automatically when running workflows.[/dim]")
        console.print("[dim]Use 'strands run <spec> --save-session' to create sessions.[/dim]")
        sys.exit(EX_OK)

    # Sort by updated_at descending (most recent first)
    sessions.sort(key=lambda s: s.updated_at, reverse=True)

    # Display as table
    table = Table(title=f"Workflow Sessions ({len(sessions)} total)")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Workflow", style="green")
    table.add_column("Pattern", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Updated", style="dim")

    for session in sessions:
        # Always show full session ID for easy copy/paste
        session_id_display = session.session_id

        # Format timestamp (show full if verbose, date only if not)
        timestamp_display = session.updated_at if verbose else session.updated_at.split("T")[0]

        # Color status
        status_color = {
            SessionStatus.RUNNING: "yellow",
            SessionStatus.PAUSED: "blue",
            SessionStatus.COMPLETED: "green",
            SessionStatus.FAILED: "red",
        }.get(session.status, "white")

        table.add_row(
            session_id_display,
            session.workflow_name,
            session.pattern_type,
            f"[{status_color}]{session.status.value}[/{status_color}]",
            timestamp_display,
        )

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Use 'strands sessions show <id>' for details[/dim]")
    console.print("[dim]Use 'strands run --resume <id>' to resume a session[/dim]")

    sys.exit(EX_OK)


@sessions_app.command("show")
def sessions_show(
    session_id: Annotated[str, typer.Argument(help="Session ID to inspect")],
) -> None:
    """Show detailed information about a session.

    Displays full session metadata, variables, runtime configuration,
    token usage, and pattern-specific state for a saved session.

    Use this to inspect session state before resuming or to debug
    workflow execution.

    Examples:
        strands sessions show abc123...
        strands sessions show $(strands sessions list --status running | head -n 1)
    """
    from strands_cli.session import SessionStatus
    from strands_cli.session.file_repository import FileSessionRepository

    repo = FileSessionRepository()

    # Load session state
    state = asyncio.run(repo.load(session_id))

    if not state:
        console.print(f"[red]Session not found:[/red] {session_id}")
        console.print()
        console.print("[dim]Use 'strands sessions list' to see available sessions[/dim]")
        sys.exit(EX_USAGE)

    # Display as panel with formatted sections
    details = f"""[cyan]Session ID:[/cyan] {state.metadata.session_id}
[cyan]Workflow:[/cyan] {state.metadata.workflow_name}
[cyan]Pattern:[/cyan] {state.metadata.pattern_type}
[cyan]Status:[/cyan] {state.metadata.status.value}
[cyan]Created:[/cyan] {state.metadata.created_at}
[cyan]Updated:[/cyan] {state.metadata.updated_at}
[cyan]Spec Hash:[/cyan] {state.metadata.spec_hash[:16]}...

[cyan]Variables:[/cyan]
{json.dumps(state.variables, indent=2)}

[cyan]Runtime Configuration:[/cyan]
{json.dumps(state.runtime_config, indent=2)}

[cyan]Token Usage:[/cyan]
  Total Input:  {state.token_usage.total_input_tokens:,}
  Total Output: {state.token_usage.total_output_tokens:,}
  Total:        {state.token_usage.total_input_tokens + state.token_usage.total_output_tokens:,}
  By Agent:     {json.dumps(state.token_usage.by_agent, indent=16)}

[cyan]Pattern State:[/cyan]
{json.dumps(state.pattern_state, indent=2)}

[cyan]Artifacts Written:[/cyan]
{json.dumps(state.artifacts_written, indent=2) if state.artifacts_written else "  (none)"}
"""

    if state.metadata.error:
        details += f"\n[red]Error:[/red]\n{state.metadata.error}"

    console.print()
    console.print(Panel(details, title=f"Session {session_id[:12]}...", border_style="cyan"))
    console.print()

    # Show next actions based on status
    if state.metadata.status in (SessionStatus.RUNNING, SessionStatus.PAUSED):
        console.print("[dim]→ Resume with:[/dim] strands run --resume " + session_id)
    elif state.metadata.status == SessionStatus.COMPLETED:
        console.print("[dim]→ Session completed successfully[/dim]")
        console.print("[dim]→ Delete with:[/dim] strands sessions delete " + session_id)
    elif state.metadata.status == SessionStatus.FAILED:
        console.print(f"[red]→ Session failed:[/red] {state.metadata.error}")
        console.print("[dim]→ Delete with:[/dim] strands sessions delete " + session_id)

    sys.exit(EX_OK)


@sessions_app.command("delete")
def sessions_delete(
    session_id: Annotated[str, typer.Argument(help="Session ID to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Delete a saved session.

    Removes the session directory and all associated files including:
    - Session metadata (session.json)
    - Pattern state (pattern_state.json)
    - Spec snapshot (spec_snapshot.yaml)
    - Agent conversation history (agents/ directory)

    This operation cannot be undone. Use with caution.

    Examples:
        strands sessions delete abc123...
        strands sessions delete abc123... --force
    """
    from strands_cli.session.file_repository import FileSessionRepository

    repo = FileSessionRepository()

    # Check if session exists
    exists = asyncio.run(repo.exists(session_id))
    if not exists:
        console.print(f"[red]Session not found:[/red] {session_id}")
        console.print()
        console.print("[dim]Use 'strands sessions list' to see available sessions[/dim]")
        sys.exit(EX_USAGE)

    # Confirm unless --force
    if not force:
        console.print(f"[yellow]Delete session {session_id[:12]}...?[/yellow]")
        console.print(
            "[dim]This will remove all session data including agent conversation history.[/dim]"
        )
        console.print()
        confirm = typer.confirm("Continue?")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            sys.exit(EX_OK)

    # Delete session
    asyncio.run(repo.delete(session_id))
    console.print(f"[green]✓[/green] Session deleted: {session_id[:12]}...")

    sys.exit(EX_OK)


@sessions_app.command("cleanup")
def sessions_cleanup(
    max_age_days: Annotated[
        int,
        typer.Option(help="Delete sessions older than this many days"),
    ] = 7,
    keep_completed: Annotated[
        bool,
        typer.Option(help="Keep completed sessions regardless of age"),
    ] = True,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Clean up expired workflow sessions.

    Removes old sessions based on age to prevent storage bloat. By default,
    keeps completed sessions for audit purposes and only removes failed/paused/running
    sessions older than the specified age.

    Examples:
        strands sessions cleanup
        strands sessions cleanup --max-age-days 30
        strands sessions cleanup --max-age-days 7 --no-keep-completed
        strands sessions cleanup --force
    """
    from strands_cli.session.cleanup import cleanup_expired_sessions
    from strands_cli.session.file_repository import FileSessionRepository

    repo = FileSessionRepository()

    # Show what will be cleaned unless --force
    if not force:
        console.print(f"[yellow]Cleanup sessions older than {max_age_days} days[/yellow]")
        if keep_completed:
            console.print("[dim]Completed sessions will be preserved[/dim]")
        else:
            console.print("[dim]All sessions (including completed) will be cleaned[/dim]")
        console.print()
        confirm = typer.confirm("Continue?")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            sys.exit(EX_OK)

    # Run cleanup
    deleted_count = asyncio.run(
        cleanup_expired_sessions(
            repo,
            max_age_days=max_age_days,
            keep_completed=keep_completed,
        )
    )

    if deleted_count > 0:
        console.print(f"[green]✓[/green] Deleted {deleted_count} expired session(s)")
    else:
        console.print("[dim]No expired sessions found[/dim]")

    sys.exit(EX_OK)


@app.command(name="list-tools")
def list_tools() -> None:
    """List all available native tools from the registry.

    Displays native tools that can be used in workflow specifications.
    These tools are auto-discovered from the src/strands_cli/tools/ directory.

    Native tools can be referenced in workflow specs using:
    - Short ID: "python_exec"
    - Full path: "strands_cli.tools.python_exec"

    Legacy strands_tools.* packages remain available for backward compatibility.
    """
    from strands_cli.tools import get_registry

    registry = get_registry()
    tools = registry.list_all()

    if not tools:
        console.print("[yellow]No native tools found in registry[/yellow]")
        console.print()
        console.print("[dim]Native tools are auto-discovered from:[/dim]")
        console.print("[dim]  src/strands_cli/tools/<tool_name>.py[/dim]")
        console.print()
        console.print("[dim]Each tool must export a TOOL_SPEC dictionary.[/dim]")
        sys.exit(EX_OK)

    # Create table
    table = Table(title="Native Tools", border_style="cyan")
    table.add_column("Tool ID", style="cyan", no_wrap=True)
    table.add_column("Module Path", style="dim")
    table.add_column("Description")

    # Add rows sorted by tool ID
    for tool in sorted(tools, key=lambda t: t.id):
        table.add_row(tool.id, tool.module_path, tool.description)

    console.print()
    console.print(table)
    console.print()
    console.print(f"[dim]Found {len(tools)} native tool(s)[/dim]")
    console.print()
    console.print("[dim]Usage in workflow specs:[/dim]")
    console.print("[dim]  tools:[/dim]")
    console.print("[dim]    python:[/dim]")
    console.print("[dim]      - python_exec  # Short ID[/dim]")
    console.print()

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

    if pysys.version_info >= (3, 12):  # noqa: UP036
        console.print(f"  [green]✓[/green] Python {python_version} (>= 3.12 required)")
        checks_passed += 1
    else:
        console.print(f"  [red]✗[/red] Python {python_version} (>= 3.12 required)")
        checks_failed += 1

    # Check 2: Schema file exists
    console.print("\n[cyan]→[/cyan] Checking schema file...")
    try:
        from strands_cli.schema.validator import get_schema

        schema = get_schema()
        console.print(
            f"  [green]✓[/green] Schema loaded: {schema.get('title', 'Unknown')} "
            f"v{schema.get('version', 'Unknown')}"
        )
        checks_passed += 1
    except Exception as e:
        console.print(f"  [red]✗[/red] Schema load failed: {e}")
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
