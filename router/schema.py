"""Canonical AgentDecision JSON Schema for both endpoints.

Send to llama.cpp via:
    {"response_format": {"type": "json_schema", "schema": AGENT_DECISION_SCHEMA}}
"""

from __future__ import annotations

AGENT_DECISION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "tool_name",
        "arguments",
        "rationale",
        "risk",
        "confidence",
        "codex_packet",
    ],
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["tool_call", "final", "escalate", "ask_user"],
        },
        "tool_name": {
            "type": "string",
            "enum": [
                "shell",
                "read_file",
                "write_file",
                "list_files",
                "grep",
                "run_tests",
                "none",
            ],
        },
        "arguments": {"type": "object"},
        "rationale": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "codex_packet": {"anyOf": [{"type": "null"}, {"type": "string"}]},
    },
}


REQUIRED_PACKET_SECTIONS: tuple[str, ...] = (
    "goal",
    "relevant files",
    "observed failure",
    "commands already run",
    "facts learned",
    "requested",
    "constraints",
)


def packet_is_complete(packet: str | None) -> bool:
    """Cheap structural check that a Codex packet has the required sections."""
    if not packet:
        return False
    lowered = packet.lower()
    return all(section in lowered for section in REQUIRED_PACKET_SECTIONS)
