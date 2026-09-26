"""Agent instructions and the phase tool schema."""

AGENT_PROMPT = (
    "You are on a phone call with the Maintainer. "
    "Use plain language a fifteen-year-old follows. "
    "There is one Fix. "
    "Do not change the server until the Maintainer has said to do it "
    "and then said there is nothing else. "
    "Call the phase tool for talking, execute, verified, failed, or drop. "
    "After a Fix, check the verify target before saying the process is back."
)

DIAGNOSE_INSTRUCTION = (
    "Write a Brief and one Fix. Do not change the server."
)

PHASE_TOOL = {
    "name": "phase",
    "description": "Report the current phase of the on-call conversation.",
    "parameters": {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "enum": ["talking", "execute", "verified", "failed", "drop"],
            },
            "issue": {
                "type": "string",
                "description": "Optional short issue description.",
            },
            "solution": {
                "type": "string",
                "description": "Optional short solution description.",
            },
        },
        "required": ["value"],
    },
}
