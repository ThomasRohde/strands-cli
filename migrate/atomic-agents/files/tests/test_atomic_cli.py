"""CLI tests for atomic commands."""

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from strands_cli.__main__ import app
from strands_cli.exit_codes import EX_OK

runner = CliRunner()


def _write_atomic_manifest(base: Path) -> Path:
    agent_dir = base / "agents" / "atomic" / "alpha"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "schemas").mkdir(exist_ok=True)
    (agent_dir / "examples").mkdir(exist_ok=True)
    
    manifest = agent_dir / "alpha.yaml"
    manifest.write_text(
        """version: 0
name: alpha
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  worker:
    prompt: Test worker
metadata:
  labels:
    strands.io/agent_type: atomic
pattern:
  type: chain
  config:
    steps:
      - agent: worker
        input: Go
""",
        encoding="utf-8",
    )
    return manifest


def test_atomic_list_and_describe() -> None:
    with runner.isolated_filesystem():
        manifest = _write_atomic_manifest(Path("."))

        result = runner.invoke(
            app,
            ["atomic", "list", "--json"],
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert result.exit_code == EX_OK
        list_payload = json.loads(result.stdout)
        assert any(item["name"] == "alpha" for item in list_payload)
        assert any(Path(item["path"]).name == "alpha.yaml" for item in list_payload)

        describe = runner.invoke(
            app,
            ["atomic", "describe", "alpha", "--format", "json"],
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert describe.exit_code == EX_OK
        data = json.loads(describe.stdout)
        assert data["name"] == "alpha"
        assert data["path"].endswith("alpha.yaml")
        assert data["labels"]["strands.io/agent_type"] == "atomic"


def test_atomic_validate() -> None:
    with runner.isolated_filesystem():
        manifest = _write_atomic_manifest(Path("."))

        result = runner.invoke(
            app,
            ["atomic", "validate", str(manifest)],
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert result.exit_code == EX_OK
        assert "Atomic manifest is valid" in result.stdout


def test_atomic_run_validates_and_writes_output(monkeypatch: Any) -> None:
    with runner.isolated_filesystem():
        base = Path(".")
        manifest = _write_atomic_manifest(base)

        # Add input/output schemas
        agent_dir = base / "agents" / "atomic" / "alpha"
        schema_dir = agent_dir / "schemas"
        input_schema = {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]}
        output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        (schema_dir / "input.json").write_text(json.dumps(input_schema), encoding="utf-8")
        (schema_dir / "output.json").write_text(json.dumps(output_schema), encoding="utf-8")

        manifest.write_text(
            manifest.read_text().replace(
                "prompt: Test worker",
                "prompt: Test worker\n    input_schema: ./schemas/input.json\n    output_schema: ./schemas/output.json",
            ),
            encoding="utf-8",
        )

        input_file = base / "input.json"
        input_file.write_text(json.dumps({"topic": "demo"}), encoding="utf-8")
        output_file = base / "out.json"

        from strands_cli.types import PatternType, RunResult

        fake_result = RunResult(
            success=True,
            message=None,
            exit_code=None,
            pattern_type=PatternType.CHAIN,
            session_id=None,
            agent_id="worker",
            last_response=json.dumps({"ok": True}),
            error=None,
            tokens_estimated=0,
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:00:01Z",
            duration_seconds=1.0,
            artifacts_written=[],
            execution_context={},
        )

        async def fake_run_single_agent(*args: Any, **kwargs: Any) -> RunResult:
            return fake_result

        monkeypatch.setattr(
            "strands_cli.exec.single_agent.run_single_agent", fake_run_single_agent
        )
        monkeypatch.setattr("strands_cli.atomic.cli.run_single_agent", fake_run_single_agent)

        result = runner.invoke(
            app,
            [
                "atomic",
                "run",
                "alpha",
                "--input-file",
                str(input_file),
                "--output-file",
                str(output_file),
            ],
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert result.exit_code == EX_OK, result.output
        assert output_file.exists()
        content = output_file.read_text()
        assert content.strip(), "Output file should not be empty"
        assert '"ok"' in content


def test_atomic_test_command(monkeypatch: Any) -> None:
    with runner.isolated_filesystem():
        base = Path(".")
        manifest = _write_atomic_manifest(base)

        agent_dir = base / "agents" / "atomic" / "alpha"
        schema_dir = agent_dir / "schemas"
        output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        (schema_dir / "output.json").write_text(json.dumps(output_schema), encoding="utf-8")

        input_file = base / "input.json"
        input_file.write_text(json.dumps({"topic": "demo"}), encoding="utf-8")

        tests_path = agent_dir / "tests.yaml"
        tests_path.write_text(
            """tests:
  - name: simple
    input: ../../../input.json
    expect:
      output_schema: ./schemas/output.json
      checks:
        - type: has_keys
          keys: ["ok"]
""",
            encoding="utf-8",
        )

        from strands_cli.types import PatternType, RunResult

        fake_result = RunResult(
            success=True,
            message=None,
            exit_code=None,
            pattern_type=PatternType.CHAIN,
            session_id=None,
            agent_id="worker",
            last_response=json.dumps({"ok": True}),
            error=None,
            tokens_estimated=0,
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:00:01Z",
            duration_seconds=1.0,
            artifacts_written=[],
            execution_context={},
        )

        async def fake_run_single_agent(*args: Any, **kwargs: Any) -> RunResult:
            return fake_result

        monkeypatch.setattr(
            "strands_cli.exec.single_agent.run_single_agent", fake_run_single_agent
        )
        monkeypatch.setattr("strands_cli.atomic.cli.run_single_agent", fake_run_single_agent)

        result = runner.invoke(
            app,
            ["atomic", "test", "alpha", "--json"],
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert result.exit_code == EX_OK, result.output
        payload = json.loads(result.stdout)
        assert payload[0]["status"] == "pass"


def test_atomic_init_scaffolds_files() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["atomic", "init", "gamma", "--domain", "demo", "--capability", "summary"],
            env={"OPENAI_API_KEY": "sk-test"},
        )

        assert result.exit_code == EX_OK, result.output

        assert Path("agents/atomic/gamma/gamma.yaml").exists()
        assert Path("agents/atomic/gamma/schemas/input.json").exists()
        assert Path("agents/atomic/gamma/schemas/output.json").exists()
        assert Path("agents/atomic/gamma/tests.yaml").exists()
        assert Path("agents/atomic/gamma/examples/sample.json").exists()
