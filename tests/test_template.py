"""Unit tests for template rendering utilities."""

import pytest
from pytest_mock import MockerFixture

from strands_cli.loader.template import TemplateError, TemplateRenderer, render_template


@pytest.mark.unit
def test_render_template_undefined_variable_raises() -> None:
    """Undefined template variables should raise TemplateError."""
    with pytest.raises(TemplateError):
        render_template("Hello {{ missing }}", {})


@pytest.mark.unit
def test_template_renderer_reuses_cached_environment(mocker: MockerFixture) -> None:
    """TemplateRenderer should reuse its sandboxed environment across renders."""
    mock_env = mocker.Mock()
    mock_template = mocker.Mock()
    mock_template.render.return_value = "Result"
    mock_env.from_string.return_value = mock_template

    mock_create_env = mocker.patch(
        "strands_cli.loader.template._create_sandboxed_environment",
        return_value=mock_env,
    )

    renderer = TemplateRenderer(max_output_chars=50)
    output = renderer.render("Hello", {})

    assert output == "Result"
    mock_create_env.assert_called_once()
    mock_env.from_string.assert_called_once_with("Hello")
    mock_template.render.assert_called_once_with()


@pytest.mark.unit
def test_template_renderer_applies_max_output_chars() -> None:
    """TemplateRenderer should respect max_output_chars truncation."""
    renderer = TemplateRenderer(max_output_chars=5)
    output = renderer.render("{{ value }}", {"value": "abcdefgh"})

    assert output == "abcde"
