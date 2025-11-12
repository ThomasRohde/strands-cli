"""Graph visualization for plan command.

Generates DOT format (Graphviz) visualization of graph pattern workflows.
"""

import structlog

from strands_cli.types import Spec

logger = structlog.get_logger(__name__)


def generate_dot(spec: Spec) -> str:
    """Generate Graphviz DOT format representation of graph pattern.

    Creates a directed graph showing:
    - Nodes as labeled boxes with agent names
    - Entry node highlighted in green
    - Terminal nodes highlighted in red
    - Static edges as solid arrows
    - Conditional edges as dashed arrows with condition labels

    Args:
        spec: Workflow spec with graph pattern

    Returns:
        DOT format string suitable for Graphviz rendering

    Example:
        >>> dot = generate_dot(spec)
        >>> # Save to file: dot -Tpng graph.dot -o graph.png
    """
    if not spec.pattern.config.nodes or not spec.pattern.config.edges:
        return "// Invalid graph: no nodes or edges"

    lines = []
    lines.append("digraph workflow {")
    lines.append("    rankdir=TB;  // Top to bottom layout")
    lines.append("    node [shape=box, style=rounded];")
    lines.append("")

    # Find entry and terminal nodes
    entry_node = next(iter(spec.pattern.config.nodes.keys()))
    nodes_with_outgoing = {edge.from_ for edge in spec.pattern.config.edges}
    terminal_nodes = set(spec.pattern.config.nodes.keys()) - nodes_with_outgoing

    # Generate nodes
    lines.append("    // Nodes")
    for node_id, node in spec.pattern.config.nodes.items():
        # Determine styling
        if node_id == entry_node:
            style = 'fillcolor=lightgreen, style="filled,rounded"'
            label = f"{node_id}\\n({node.agent})\\n[ENTRY]"
        elif node_id in terminal_nodes:
            style = 'fillcolor=lightcoral, style="filled,rounded"'
            label = f"{node_id}\\n({node.agent})\\n[TERMINAL]"
        else:
            style = ""
            label = f"{node_id}\\n({node.agent})"

        if style:
            lines.append(f'    "{node_id}" [label="{label}", {style}];')
        else:
            lines.append(f'    "{node_id}" [label="{label}"];')

    lines.append("")

    # Generate edges
    lines.append("    // Edges")
    for edge in spec.pattern.config.edges:
        # Static edges (solid arrows)
        if edge.to:
            for target in edge.to:
                lines.append(f'    "{edge.from_}" -> "{target}";')

        # Conditional edges (dashed arrows with labels)
        if edge.choose:
            for choice in edge.choose:
                # Truncate long conditions for readability
                condition = choice.when
                if len(condition) > 30:
                    condition = condition[:27] + "..."

                # Escape quotes in condition
                condition = condition.replace('"', '\\"')

                lines.append(
                    f'    "{edge.from_}" -> "{choice.to}" [label="{condition}", style=dashed];'
                )

    lines.append("}")

    return "\n".join(lines)


def generate_text_visualization(spec: Spec) -> str:
    """Generate simple text-based visualization of graph.

    Fallback for environments without Graphviz.
    Shows nodes, edges, and connectivity in plain text.

    Args:
        spec: Workflow spec with graph pattern

    Returns:
        Multi-line string with text graph representation
    """
    if not spec.pattern.config.nodes or not spec.pattern.config.edges:
        return "Invalid graph: no nodes or edges"

    lines = []
    lines.append("Graph Structure")
    lines.append("=" * 50)
    lines.append("")

    # Entry node
    entry_node = next(iter(spec.pattern.config.nodes.keys()))
    lines.append(f"Entry Node: {entry_node}")
    lines.append("")

    # Terminal nodes
    nodes_with_outgoing = {edge.from_ for edge in spec.pattern.config.edges}
    terminal_nodes = set(spec.pattern.config.nodes.keys()) - nodes_with_outgoing
    if terminal_nodes:
        lines.append(f"Terminal Nodes: {', '.join(sorted(terminal_nodes))}")
    else:
        lines.append("Terminal Nodes: None (possible infinite loop!)")
    lines.append("")

    # Nodes
    lines.append("Nodes:")
    for node_id, node in spec.pattern.config.nodes.items():
        marker = ""
        if node_id == entry_node:
            marker = " [ENTRY]"
        elif node_id in terminal_nodes:
            marker = " [TERMINAL]"
        lines.append(f"  • {node_id} → agent: {node.agent}{marker}")
    lines.append("")

    # Edges
    lines.append("Edges:")
    for edge in spec.pattern.config.edges:
        # Static edges
        if edge.to:
            targets = ", ".join(edge.to)
            lines.append(f"  {edge.from_} → {targets}")

        # Conditional edges
        if edge.choose:
            lines.append(f"  {edge.from_} →")
            for choice in edge.choose:
                condition = choice.when
                if len(condition) > 50:
                    condition = condition[:47] + "..."
                lines.append(f"    ├─ if {condition} → {choice.to}")

    lines.append("")
    lines.append("=" * 50)

    return "\n".join(lines)
