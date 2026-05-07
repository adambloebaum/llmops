"""Codex packet construction + validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import REQUIRED_PACKET_SECTIONS


@dataclass
class CodexPacket:
    goal: str
    relevant_files: list[tuple[str, str]] = field(default_factory=list)
    observed_failure: dict = field(default_factory=dict)  # command, output_summary, exact_error
    commands_run: list[str] = field(default_factory=list)
    facts_learned: list[str] = field(default_factory=list)
    hypothesis: str = ""
    local_attempts: list[str] = field(default_factory=list)
    requested_action: str = ""
    constraints: list[str] = field(default_factory=lambda: [
        "no unrelated refactors",
        "preserve existing behavior unless tests indicate otherwise",
        "include tests or update failing tests only if behavior intentionally changes",
    ])

    def render(self) -> str:
        lines: list[str] = []
        lines.append("Goal:")
        lines.append(f"- {self.goal}")
        lines.append("")
        lines.append("Relevant files:")
        for path, why in self.relevant_files:
            lines.append(f"- {path}: {why}")
        lines.append("")
        of = self.observed_failure
        lines.append("Observed failure:")
        lines.append(f"- command: {of.get('command', '')}")
        lines.append(f"- output summary: {of.get('output_summary', '')}")
        lines.append(f"- exact failing assertion/error: {of.get('exact_error', '')}")
        lines.append("")
        lines.append("Commands already run:")
        for cmd in self.commands_run:
            lines.append(f"- {cmd}")
        lines.append("")
        lines.append("Facts learned:")
        for fact in self.facts_learned:
            lines.append(f"- {fact}")
        lines.append("")
        lines.append("Hypothesis:")
        lines.append(f"- {self.hypothesis}")
        lines.append("")
        lines.append("Local attempts:")
        for attempt in self.local_attempts:
            lines.append(f"- {attempt}")
        lines.append("")
        lines.append("Requested Codex action:")
        lines.append(f"- {self.requested_action}")
        lines.append("")
        lines.append("Constraints:")
        for c in self.constraints:
            lines.append(f"- {c}")
        return "\n".join(lines)


def validate_rendered(packet_text: str) -> tuple[bool, list[str]]:
    """Return (ok, missing_sections)."""
    lowered = packet_text.lower()
    missing = [s for s in REQUIRED_PACKET_SECTIONS if s not in lowered]
    return (not missing, missing)
