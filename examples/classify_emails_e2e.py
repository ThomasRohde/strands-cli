#!/usr/bin/env python3
"""End-to-end example that classifies customer emails with an atomic agent."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from strands_cli.api import Workflow

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = Path(__file__).resolve().parent
DATA_PATH = EXAMPLES_DIR / "data" / "emails.json"
ATOMIC_SPEC = ROOT / "agents" / "atomic" / "classify_ticket_priority" / "classify_ticket_priority.yaml"
ARTIFACT_PATH = ROOT / "artifacts" / "emails_classified.json"

console = Console()


def _load_email_data() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Sample data not found at {DATA_PATH}")
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _parse_classification(raw_response: str | None) -> dict[str, Any]:
    if not raw_response:
        return {"priority": "unknown", "rationale": "", "raw_response": raw_response}

    try:
        payload = json.loads(raw_response)
        if isinstance(payload, dict):
            return {
                "priority": payload.get("priority", "unknown"),
                "rationale": payload.get("rationale", ""),
                "raw_response": raw_response,
            }
    except json.JSONDecodeError:
        pass

    return {
        "priority": "unknown",
        "rationale": raw_response.strip(),
        "raw_response": raw_response,
    }


def _ensure_artifact_directory() -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)


async def _classify_email(record: dict[str, Any]) -> dict[str, Any]:
    workflow = Workflow.from_file(
        ATOMIC_SPEC,
        subject=record.get("subject", ""),
        body=record.get("body", ""),
    )

    result = await workflow.run_async()
    contract = _parse_classification(result.last_response)

    return {
        **record,
        "classification": {
            "priority": contract["priority"],
            "rationale": contract["rationale"],
            "raw_response": contract["raw_response"],
            "duration_seconds": result.duration_seconds,
            "agent_id": result.agent_id,
            "session_id": result.session_id,
        },
    }


async def classify_emails() -> dict[str, Any]:
    console.print("[bold cyan]\nClassifying sample emails with atomic agents...[/bold cyan]")
    emails = _load_email_data()
    classified: list[dict[str, Any]] = []

    for record in emails:
        console.print(f"[cyan]- Running classification for {record.get('id')} ({record.get('subject')})")
        enriched = await _classify_email(record)
        classified.append(enriched)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_data": str(DATA_PATH.relative_to(ROOT)),
        "agent_spec": str(ATOMIC_SPEC.relative_to(ROOT)),
        "total_emails": len(classified),
        "items": classified,
    }

    _ensure_artifact_directory()
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"[green]Saved classifications to {ARTIFACT_PATH}[/green]")
    return payload


def main() -> None:
    asyncio.run(classify_emails())


if __name__ == "__main__":
    main()
