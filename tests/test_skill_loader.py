"""Tests for skill loader tool factory."""

import tempfile
from pathlib import Path

import pytest

from strands_cli.tools.skill_loader import create_skill_loader_tool
from strands_cli.types import Skill


@pytest.fixture
def temp_skill_dir():
    """Create a temporary directory with skill files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test_skill"
        skill_dir.mkdir()

        # Create SKILL.md
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "# Test Skill\n\nThis is a test skill with detailed instructions.\n\n"
            "## Usage\n\nFollow these steps:\n1. Step one\n2. Step two"
        )

        yield skill_dir


@pytest.fixture
def minimal_spec(temp_skill_dir):
    """Create a minimal spec with skills."""
    from unittest.mock import MagicMock

    # Create a mock spec with just the skills attribute
    spec = MagicMock()
    spec.skills = [
        Skill(
            id="test_skill",
            path=str(temp_skill_dir),
            description="A test skill for unit tests",
        )
    ]
    spec._spec_dir = str(temp_skill_dir.parent)

    return spec


def test_create_skill_loader_tool_success(minimal_spec):
    """Test creating skill loader tool with valid spec."""
    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(minimal_spec._spec_dir), loaded_skills)

    # Verify tool module structure
    assert hasattr(tool_module, "TOOL_SPEC")
    assert hasattr(tool_module, "Skill")
    assert hasattr(tool_module, "_spec")
    assert hasattr(tool_module, "_spec_dir")
    assert hasattr(tool_module, "_loaded_skills")

    # Verify TOOL_SPEC
    assert tool_module.TOOL_SPEC["name"] == "Skill"
    assert "skill_id" in tool_module.TOOL_SPEC["inputSchema"]["json"]["properties"]


def test_skill_loader_load_skill_success(minimal_spec, temp_skill_dir):
    """Test successfully loading a skill."""
    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool
    result = tool_module.Skill(
        {
            "toolUseId": "test-123",
            "input": {"skill_id": "test_skill"},
        }
    )

    # Verify success
    assert result["toolUseId"] == "test-123"
    assert result["status"] == "success"
    assert len(result["content"]) == 1
    assert "Test Skill" in result["content"][0]["text"]
    assert "detailed instructions" in result["content"][0]["text"]

    # Verify skill marked as loaded
    assert "test_skill" in loaded_skills


def test_skill_loader_skill_not_found(minimal_spec, temp_skill_dir):
    """Test loading a non-existent skill."""
    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool with invalid ID
    result = tool_module.Skill(
        {
            "toolUseId": "test-456",
            "input": {"skill_id": "nonexistent_skill"},
        }
    )

    # Verify error
    assert result["toolUseId"] == "test-456"
    assert result["status"] == "error"
    assert "not found" in result["content"][0]["text"]
    assert "test_skill" in result["content"][0]["text"]  # Available skills list


def test_skill_loader_missing_skill_id(minimal_spec, temp_skill_dir):
    """Test calling Skill tool without skill_id parameter."""
    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool without skill_id
    result = tool_module.Skill(
        {
            "toolUseId": "test-789",
            "input": {},
        }
    )

    # Verify error
    assert result["toolUseId"] == "test-789"
    assert result["status"] == "error"
    assert "required" in result["content"][0]["text"]


def test_skill_loader_already_loaded(minimal_spec, temp_skill_dir):
    """Test loading a skill that's already been loaded."""
    loaded_skills = {"test_skill"}  # Pre-populate
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool for already-loaded skill
    result = tool_module.Skill(
        {
            "toolUseId": "test-000",
            "input": {"skill_id": "test_skill"},
        }
    )

    # Verify warning (success status but with message)
    assert result["toolUseId"] == "test-000"
    assert result["status"] == "success"
    assert "already loaded" in result["content"][0]["text"]


def test_skill_loader_missing_skill_file(minimal_spec, temp_skill_dir):
    """Test loading a skill with no SKILL.md or README.md."""
    # Create a skill with no files
    empty_skill_dir = temp_skill_dir.parent / "empty_skill"
    empty_skill_dir.mkdir()

    # Add skill to spec
    minimal_spec.skills.append(
        Skill(
            id="empty_skill",
            path=str(empty_skill_dir),
            description="Empty skill",
        )
    )

    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool
    result = tool_module.Skill(
        {
            "toolUseId": "test-111",
            "input": {"skill_id": "empty_skill"},
        }
    )

    # Verify error
    assert result["toolUseId"] == "test-111"
    assert result["status"] == "error"
    assert "no SKILL.md or README.md" in result["content"][0]["text"]


def test_skill_loader_readme_fallback(minimal_spec, temp_skill_dir):
    """Test loading skill with README.md when SKILL.md doesn't exist."""
    # Create a skill with README.md only
    readme_skill_dir = temp_skill_dir.parent / "readme_skill"
    readme_skill_dir.mkdir()
    readme_file = readme_skill_dir / "README.md"
    readme_file.write_text("# README Skill\n\nThis skill uses README.md instead of SKILL.md.")

    # Add skill to spec
    minimal_spec.skills.append(
        Skill(
            id="readme_skill",
            path=str(readme_skill_dir),
            description="README-based skill",
        )
    )

    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool
    result = tool_module.Skill(
        {
            "toolUseId": "test-222",
            "input": {"skill_id": "readme_skill"},
        }
    )

    # Verify success
    assert result["toolUseId"] == "test-222"
    assert result["status"] == "success"
    assert "README Skill" in result["content"][0]["text"]
    assert "readme_skill" in loaded_skills


def test_skill_loader_skill_no_path(minimal_spec, temp_skill_dir):
    """Test loading skill with no path defined."""
    # Add skill without path
    minimal_spec.skills.append(
        Skill(
            id="no_path_skill",
            path=None,
            description="Skill without path",
        )
    )

    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool
    result = tool_module.Skill(
        {
            "toolUseId": "test-333",
            "input": {"skill_id": "no_path_skill"},
        }
    )

    # Verify error
    assert result["toolUseId"] == "test-333"
    assert result["status"] == "error"
    assert "no path defined" in result["content"][0]["text"]


def test_skill_loader_content_formatting(minimal_spec, temp_skill_dir):
    """Test that skill content is properly formatted."""
    loaded_skills = set()
    tool_module = create_skill_loader_tool(minimal_spec, str(temp_skill_dir.parent), loaded_skills)

    # Invoke Skill tool
    result = tool_module.Skill(
        {
            "toolUseId": "test-444",
            "input": {"skill_id": "test_skill"},
        }
    )

    # Verify formatting
    content = result["content"][0]["text"]
    assert content.startswith("# Loaded Skill: test_skill")
    assert "**Description**: A test skill for unit tests" in content
    assert "---" in content  # Separator
    assert "# Test Skill" in content  # Original skill content
