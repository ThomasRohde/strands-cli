"""Interactive variable prompting with type coercion.

This module provides functionality to interactively prompt users for missing variables
with automatic type coercion based on the parameter schema.
"""

from __future__ import annotations

import sys
from typing import Any

import structlog
from rich.console import Console
from rich.prompt import Prompt

from strands_cli.loader.variable_detector import (
    extract_param_info,
    get_variable_metadata,
)

logger = structlog.get_logger(__name__)
console = Console()


def is_interactive() -> bool:
    """Check if stdin is connected to a TTY (interactive terminal).

    Returns:
        True if stdin is a TTY, False otherwise (e.g., in CI/CD, piped input)
    """
    return sys.stdin.isatty()


def coerce_value(raw_value: str, param_type: str) -> str | int | float | bool:
    """Coerce a string value to the appropriate type.

    Args:
        raw_value: The raw string value from user input
        param_type: Expected type ("string", "integer", "number", "boolean")

    Returns:
        Coerced value in the appropriate Python type

    Raises:
        ValueError: If value cannot be coerced to the expected type

    Examples:
        >>> coerce_value("42", "integer")
        42
        >>> coerce_value("3.14", "number")
        3.14
        >>> coerce_value("true", "boolean")
        True
        >>> coerce_value("hello", "string")
        'hello'
    """
    if param_type == "string":
        return raw_value

    if param_type == "integer":
        try:
            return int(raw_value)
        except ValueError as e:
            raise ValueError(f"Cannot convert '{raw_value}' to integer") from e

    if param_type == "number":
        try:
            return float(raw_value)
        except ValueError as e:
            raise ValueError(f"Cannot convert '{raw_value}' to number") from e

    if param_type == "boolean":
        # Accept common boolean representations
        lower_value = raw_value.lower().strip()
        if lower_value in ("true", "yes", "y", "1"):
            return True
        if lower_value in ("false", "no", "n", "0"):
            return False
        raise ValueError(
            f"Cannot convert '{raw_value}' to boolean (use: true/false, yes/no, y/n, 1/0)"
        )

    # Unknown type - treat as string
    logger.warning(
        "variable.prompt.unknown_type",
        param_type=param_type,
        fallback="string",
    )
    return raw_value


def prompt_for_variable(spec: Any, var_name: str) -> str | int | float | bool:
    """Interactively prompt user for a missing variable value.

    Args:
        spec: The validated workflow specification
        var_name: Name of the variable to prompt for

    Returns:
        User-provided value, coerced to the appropriate type

    Raises:
        ValueError: If value cannot be coerced to expected type
        KeyError: If variable not found in spec inputs

    Examples:
        >>> prompt_for_variable(spec, "topic")  # User enters "AI safety"
        'AI safety'
        >>> prompt_for_variable(spec, "user_id")  # User enters "42"
        42
    """
    from rich.panel import Panel

    # Get parameter metadata from spec
    param_spec, _ = get_variable_metadata(spec, var_name)
    param_info = extract_param_info(param_spec)
    param_type = param_info["type"]

    # Build rich panel content
    panel_lines = []

    # Variable name and description
    panel_lines.append(f"[bold white]{var_name}[/bold white]")
    if param_info["description"]:
        panel_lines.append(f"[dim]{param_info['description']}[/dim]")

    panel_lines.append("")  # Blank line

    # Type information
    if param_type != "string":
        panel_lines.append(f"[yellow]Type:[/yellow] {param_type}")

    # Enum choices
    if param_info["enum"]:
        enum_display = ", ".join(f"[cyan]{v}[/cyan]" for v in param_info["enum"])
        panel_lines.append(f"[yellow]Choices:[/yellow] {enum_display}")

    # Examples based on type
    examples = {
        "string": "AI safety alignment",
        "integer": "42",
        "number": "3.14",
        "boolean": "true",
    }
    if param_type in examples and not param_info["enum"]:
        panel_lines.append(f"[dim]Example: {examples[param_type]}[/dim]")
    elif param_info["enum"] and param_info["enum"]:
        panel_lines.append(f"[dim]Example: {param_info['enum'][0]}[/dim]")

    # Display panel
    console.print()
    console.print(
        Panel(
            "\n".join(panel_lines),
            title="[bold cyan]Variable Input[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
    )

    # Prompt user with clear instruction
    raw_value = Prompt.ask("[bold cyan]Enter value[/bold cyan]", console=console)

    logger.debug(
        "variable.prompt.input",
        var_name=var_name,
        raw_value=raw_value,
        param_type=param_type,
    )

    # Coerce to expected type
    try:
        coerced_value = coerce_value(raw_value, param_type)
        logger.debug(
            "variable.prompt.coerced",
            var_name=var_name,
            coerced_value=coerced_value,
            coerced_type=type(coerced_value).__name__,
        )
        console.print(f"[green]✓[/green] [dim]Accepted: {coerced_value}[/dim]")
        return coerced_value
    except ValueError as e:
        console.print(f"\n[red]✗ Invalid input:[/red] {e}")
        console.print("[dim]Please try again...\n[/dim]")
        return prompt_for_variable(spec, var_name)


def prompt_for_missing_variables(
    spec: Any, missing_vars: list[str]
) -> dict[str, str | int | float | bool]:
    """Prompt user for all missing variables.

    Args:
        spec: The validated workflow specification
        missing_vars: List of variable names to prompt for

    Returns:
        Dictionary mapping variable names to user-provided values

    Examples:
        >>> prompt_for_missing_variables(spec, ["topic", "user_id"])
        {'topic': 'AI safety', 'user_id': 42}
    """
    from rich.panel import Panel

    if not missing_vars:
        return {}

    # Show header panel with instructions and variable list
    header_lines = [
        f"[yellow]⚠[/yellow]  [bold]Required variables missing: {len(missing_vars)}[/bold]\n"
    ]

    # List all missing variables
    header_lines.append("[white]Variables to provide:[/white]")
    for i, var_name in enumerate(missing_vars, 1):
        header_lines.append(f"  [cyan]{i}.[/cyan] {var_name}")

    header_lines.append("")  # Blank line
    header_lines.append("[dim]Please provide values for each variable.")
    header_lines.append("Simply type your answer and press Enter.[/dim]")

    header_content = "\n".join(header_lines)

    console.print()
    console.print(
        Panel(
            header_content,
            title="[bold cyan]Interactive Variable Input[/bold cyan]",
            border_style="yellow",
            padding=(0, 1),
        )
    )

    prompted_values = {}
    for var_name in missing_vars:
        try:
            value = prompt_for_variable(spec, var_name)
            prompted_values[var_name] = value
        except KeyError as e:
            # Variable not in spec (shouldn't happen if detection is correct)
            logger.error(
                "variable.prompt.not_found",
                var_name=var_name,
                error=str(e),
            )
            console.print(f"[red]Error:[/red] Variable '{var_name}' not found in spec")
            raise

    # Show completion summary
    from rich.panel import Panel

    summary_lines = ["[green]✓[/green] [bold]All variables collected successfully![/bold]\n"]
    for var_name, value in prompted_values.items():
        # Truncate long values for display
        display_value = str(value)
        if len(display_value) > 60:
            display_value = display_value[:57] + "..."
        summary_lines.append(f"  [cyan]{var_name}[/cyan]: [white]{display_value}[/white]")

    console.print()
    console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold green]Variables Collected[/bold green]",
            border_style="green",
            padding=(0, 1),
        )
    )
    console.print()

    return prompted_values
