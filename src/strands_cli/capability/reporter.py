"""Generate capability reports for unsupported features.

Provides human-readable and machine-readable reports when workflows
contain unsupported features. Reports include:

- Spec fingerprint (SHA-256) for tracking
- Detailed issue list with JSONPointer locations
- Specific remediation steps for each issue
- Minimal working example for reference

Report Formats:
    - Markdown: Human-readable with formatting for readability
    - JSON: Structured data for programmatic processing
"""

import hashlib
import json

from strands_cli.types import CapabilityReport


def generate_markdown_report(spec_path: str, spec_content: str, report: CapabilityReport) -> str:
    """Generate a Markdown report for unsupported features.

    Creates a comprehensive report with:
    - Spec metadata (path, fingerprint, issue count)
    - Detailed issue breakdown with remediation steps
    - Minimal working example
    - Next steps guidance

    Args:
        spec_path: Path to the original spec file (for reference)
        spec_content: Raw content of the spec file (for fingerprinting)
        report: Capability report with unsupported feature issues

    Returns:
        Markdown-formatted report suitable for file output or display
    """
    # Calculate spec fingerprint
    fingerprint = hashlib.sha256(spec_content.encode("utf-8")).hexdigest()[:16]

    lines = [
        "# Strands CLI: Unsupported Features Report",
        "",
        f"**Spec File:** `{spec_path}`  ",
        f"**Fingerprint:** `{fingerprint}`  ",
        f"**Issues Found:** {len(report.issues)}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "This workflow specification contains features that are not yet supported in the current MVP.",
        "Please review the issues below and apply the suggested remediations.",
        "",
    ]

    # List issues
    if report.issues:
        lines.extend(
            [
                "## Issues",
                "",
            ]
        )

        for i, issue in enumerate(report.issues, 1):
            lines.extend(
                [
                    f"### {i}. `{issue.pointer}`",
                    "",
                    f"**Reason:** {issue.reason}  ",
                    f"**Remediation:** {issue.remediation}",
                    "",
                ]
            )

    # Add minimal example
    lines.extend(
        [
            "---",
            "",
            "## Minimal Runnable Example",
            "",
            "Here's a minimal single-agent workflow that is supported in MVP:",
            "",
            "```yaml",
            "version: 0",
            "name: minimal-single-agent",
            "",
            "runtime:",
            "  provider: ollama",
            "  model_id: gpt-oss",
            "  host: http://localhost:11434",
            "",
            "agents:",
            "  main:",
            "    prompt: You are a helpful assistant.",
            "",
            "pattern:",
            "  type: chain",
            "  config:",
            "    steps:",
            "      - agent: main",
            '        input: "Process this task."',
            "",
            "outputs:",
            "  artifacts:",
            "    - path: ./artifacts/output.md",
            "      from: '{{ last_response }}'",
            "```",
            "",
            "---",
            "",
            "## Next Steps",
            "",
            "1. Review the issues listed above",
            "2. Apply suggested remediations to your spec",
            "3. Run `strands-cli validate <spec>` to verify changes",
            "4. Run `strands-cli plan <spec>` to preview execution",
            "5. Run `strands-cli run <spec>` to execute",
            "",
        ]
    )

    return "\n".join(lines)


def generate_json_report(spec_path: str, spec_content: str, report: CapabilityReport) -> str:
    """Generate a JSON report for unsupported features.

    Args:
        spec_path: Path to the original spec file
        spec_content: Raw content of the spec file
        report: Capability report with issues

    Returns:
        JSON-formatted report
    """
    fingerprint = hashlib.sha256(spec_content.encode("utf-8")).hexdigest()[:16]

    report_data = {
        "spec_path": spec_path,
        "fingerprint": fingerprint,
        "supported": report.supported,
        "issues_count": len(report.issues),
        "issues": [
            {
                "pointer": issue.pointer,
                "reason": issue.reason,
                "remediation": issue.remediation,
            }
            for issue in report.issues
        ],
    }

    return json.dumps(report_data, indent=2)
