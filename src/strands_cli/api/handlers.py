"""Interactive HITL handlers for terminal prompts."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from strands_cli.types import HITLState


def terminal_hitl_handler(hitl_state: HITLState) -> str:
    """Default terminal prompt handler for interactive HITL.

    Displays HITL prompt with Rich formatting and optional context,
    then prompts user for input via standard input.

    Args:
        hitl_state: HITL pause state with prompt/context

    Returns:
        User's response string

    Example:
        >>> from strands_cli.types import HITLState
        >>> state = HITLState(
        ...     active=True,
        ...     prompt="Approve findings?",
        ...     context_display="Research results: ...",
        ... )
        >>> response = terminal_hitl_handler(state)
    """
    console = Console()

    # Display HITL prompt
    console.print()
    console.print(
        Panel(
            f"[bold yellow]🤝 HUMAN INPUT REQUIRED[/bold yellow]\n\n{hitl_state.prompt}",
            border_style="yellow",
            padding=(1, 2),
            title="Interactive HITL",
        )
    )

    # Display context if provided
    if hitl_state.context_display:
        # Truncate long context for readability
        context = hitl_state.context_display
        truncated = False
        if len(context) > 1000:
            context = context[:1000]
            truncated = True

        console.print()
        console.print(
            Panel(
                f"[bold]Context:[/bold]\n\n{context}",
                border_style="dim",
                padding=(1, 2),
            )
        )

        if truncated:
            console.print("[dim](Context truncated for display)[/dim]")

    # Show default if provided
    if hitl_state.default_response:
        console.print(f"\n[dim]Default (press Enter):[/dim] {hitl_state.default_response}")

    # Prompt for user input
    console.print()
    response = Prompt.ask("Your response")

    # Use default if empty and default is provided
    if not response.strip() and hitl_state.default_response:
        console.print(f"[dim]Using default: {hitl_state.default_response}[/dim]")
        return hitl_state.default_response

    return response.strip()


__all__ = ["terminal_hitl_handler"]
