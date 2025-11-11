"""Tests for capability reporter.

Tests the generation of Markdown and JSON reports for unsupported features.
"""

import json

from strands_cli.capability.reporter import generate_json_report, generate_markdown_report
from strands_cli.types import CapabilityIssue, CapabilityReport


def test_generate_markdown_report_basic() -> None:
    """Test generating a basic Markdown report."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/runtime/provider",
                reason="Provider 'azure' not supported",
                remediation="Use 'bedrock', 'ollama', or 'openai'",
            )
        ],
    )

    result = generate_markdown_report("test.yaml", "version: 0\nname: test", report)

    # Check report structure
    assert "# Strands CLI: Unsupported Features Report" in result
    assert "**Spec File:** `test.yaml`" in result
    assert "**Issues Found:** 1" in result
    assert "/runtime/provider" in result
    assert "Provider 'azure' not supported" in result
    assert "Use 'bedrock', 'ollama', or 'openai'" in result


def test_generate_markdown_report_multiple_issues() -> None:
    """Test generating report with multiple issues."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/runtime/provider",
                reason="Provider not supported",
                remediation="Use supported provider",
            ),
            CapabilityIssue(
                pointer="/pattern/type",
                reason="Pattern not supported",
                remediation="Use supported pattern",
            ),
        ],
    )

    result = generate_markdown_report("test.yaml", "version: 0", report)

    assert "**Issues Found:** 2" in result
    assert "/runtime/provider" in result
    assert "/pattern/type" in result
    assert "### 1." in result
    assert "### 2." in result


def test_generate_markdown_report_includes_minimal_example() -> None:
    """Test that report includes minimal working example."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/test",
                reason="Test",
                remediation="Fix it",
            )
        ],
    )

    result = generate_markdown_report("test.yaml", "version: 0", report)

    # Check minimal example is included
    assert "## Minimal Runnable Example" in result
    assert "version: 0" in result
    assert "name: minimal-single-agent" in result
    assert "provider: ollama" in result
    assert "pattern:" in result
    assert "type: chain" in result


def test_generate_markdown_report_includes_next_steps() -> None:
    """Test that report includes next steps."""
    report = CapabilityReport(supported=False, issues=[])

    result = generate_markdown_report("test.yaml", "version: 0", report)

    assert "## Next Steps" in result
    assert "strands-cli validate" in result
    assert "strands-cli plan" in result
    assert "strands-cli run" in result


def test_generate_markdown_report_calculates_fingerprint() -> None:
    """Test that report includes spec fingerprint."""
    spec_content = "version: 0\nname: test-workflow"

    report = CapabilityReport(supported=False, issues=[])

    result = generate_markdown_report("test.yaml", spec_content, report)

    assert "**Fingerprint:**" in result
    # Fingerprint should be consistent for same content
    result2 = generate_markdown_report("test.yaml", spec_content, report)
    assert result == result2


def test_generate_markdown_report_empty_issues() -> None:
    """Test generating report with no issues."""
    report = CapabilityReport(supported=True, issues=[])

    result = generate_markdown_report("test.yaml", "version: 0", report)

    assert "**Issues Found:** 0" in result
    # Should still include minimal example and next steps
    assert "## Minimal Runnable Example" in result
    assert "## Next Steps" in result


def test_generate_json_report_basic() -> None:
    """Test generating a basic JSON report."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/runtime/provider",
                reason="Provider not supported",
                remediation="Use supported provider",
            )
        ],
    )

    result = generate_json_report("test.yaml", "version: 0\nname: test", report)

    # Parse JSON
    data = json.loads(result)

    assert data["spec_path"] == "test.yaml"
    assert data["supported"] is False
    assert data["issues_count"] == 1
    assert len(data["issues"]) == 1
    assert data["issues"][0]["pointer"] == "/runtime/provider"
    assert data["issues"][0]["reason"] == "Provider not supported"
    assert data["issues"][0]["remediation"] == "Use supported provider"
    assert "fingerprint" in data


def test_generate_json_report_multiple_issues() -> None:
    """Test generating JSON report with multiple issues."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/runtime/provider",
                reason="Provider issue",
                remediation="Fix provider",
            ),
            CapabilityIssue(
                pointer="/pattern/type",
                reason="Pattern issue",
                remediation="Fix pattern",
            ),
        ],
    )

    result = generate_json_report("test.yaml", "version: 0", report)

    data = json.loads(result)

    assert data["issues_count"] == 2
    assert len(data["issues"]) == 2
    assert data["issues"][0]["pointer"] == "/runtime/provider"
    assert data["issues"][1]["pointer"] == "/pattern/type"


def test_generate_json_report_empty_issues() -> None:
    """Test generating JSON report with no issues."""
    report = CapabilityReport(supported=True, issues=[])

    result = generate_json_report("test.yaml", "version: 0", report)

    data = json.loads(result)

    assert data["supported"] is True
    assert data["issues_count"] == 0
    assert len(data["issues"]) == 0


def test_generate_json_report_valid_json() -> None:
    """Test that generated JSON is valid and properly formatted."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/test",
                reason="Test reason",
                remediation="Test remediation",
            )
        ],
    )

    result = generate_json_report("test.yaml", "version: 0", report)

    # Should be valid JSON
    data = json.loads(result)

    # Should be pretty-printed (indented)
    assert "\n" in result
    assert "  " in result  # Indentation

    # Round-trip should work
    re_encoded = json.dumps(data, indent=2)
    assert json.loads(re_encoded) == data


def test_generate_json_report_fingerprint_consistency() -> None:
    """Test that fingerprint is consistent for same spec content."""
    report = CapabilityReport(supported=False, issues=[])

    spec_content = "version: 0\nname: test"

    result1 = generate_json_report("test.yaml", spec_content, report)
    result2 = generate_json_report("test.yaml", spec_content, report)

    data1 = json.loads(result1)
    data2 = json.loads(result2)

    assert data1["fingerprint"] == data2["fingerprint"]


def test_generate_json_report_fingerprint_changes() -> None:
    """Test that fingerprint changes when spec content changes."""
    report = CapabilityReport(supported=False, issues=[])

    result1 = generate_json_report("test.yaml", "version: 0\nname: test1", report)
    result2 = generate_json_report("test.yaml", "version: 0\nname: test2", report)

    data1 = json.loads(result1)
    data2 = json.loads(result2)

    assert data1["fingerprint"] != data2["fingerprint"]


def test_markdown_report_formatting() -> None:
    """Test that Markdown report has proper formatting."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/test/path",
                reason="Test reason with special chars: <>&\"'",
                remediation="Test remediation with code `example`",
            )
        ],
    )

    result = generate_markdown_report("test.yaml", "version: 0", report)

    # Should have proper Markdown structure
    assert result.startswith("# Strands CLI:")
    assert "---" in result  # Horizontal rules
    assert "```yaml" in result  # Code blocks
    assert "```" in result
    assert "**" in result  # Bold text
    assert "`" in result  # Inline code


def test_markdown_report_issue_numbering() -> None:
    """Test that issues are properly numbered in Markdown."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(pointer="/issue1", reason="R1", remediation="Fix1"),
            CapabilityIssue(pointer="/issue2", reason="R2", remediation="Fix2"),
            CapabilityIssue(pointer="/issue3", reason="R3", remediation="Fix3"),
        ],
    )

    result = generate_markdown_report("test.yaml", "version: 0", report)

    # Check proper numbering
    assert "### 1. `/issue1`" in result
    assert "### 2. `/issue2`" in result
    assert "### 3. `/issue3`" in result


def test_json_report_all_fields() -> None:
    """Test that JSON report includes all expected fields."""
    report = CapabilityReport(
        supported=False,
        issues=[
            CapabilityIssue(
                pointer="/test",
                reason="reason",
                remediation="remediation",
            )
        ],
    )

    result = generate_json_report("my-spec.yaml", "version: 0", report)
    data = json.loads(result)

    # Check all top-level fields
    assert "spec_path" in data
    assert "fingerprint" in data
    assert "supported" in data
    assert "issues_count" in data
    assert "issues" in data

    # Check issue fields
    issue = data["issues"][0]
    assert "pointer" in issue
    assert "reason" in issue
    assert "remediation" in issue
