"""`opencode run --format json` output captured from opencode 2.4.0 on 2026-11-24.

The lines keep their real shape; long ids are shortened.
"""

import json

SESSION_ID = "ses_df1f5953fffe0sTA1HHPUux5hk"

_STEP_START = {
    "type": "step_start",
    "timestamp": 1795531895953,
    "sessionID": SESSION_ID,
    "part": {"id": "prt_1", "sessionID": SESSION_ID, "messageID": "msg_1", "type": "step-start"},
}
_STEP_FINISH = {
    "type": "step_finish",
    "timestamp": 1795531895987,
    "sessionID": SESSION_ID,
    "part": {
        "id": "prt_3",
        "type": "step-finish",
        "reason": "stop",
        "cost": 0,
        "tokens": {"input": 1, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}},
    },
}


def text_event(text: str, session_id: str = SESSION_ID) -> dict:
    return {
        "type": "text",
        "timestamp": 1795531895976,
        "sessionID": session_id,
        "part": {
            "id": "prt_2",
            "sessionID": session_id,
            "messageID": "msg_1",
            "type": "text",
            "text": text,
            "time": {"start": 1795531895966, "end": 1795531895976},
        },
    }


def error_event(error: object, session_id: str = "ses_df2227066ffeJDiIgMrH5Pndcg") -> dict:
    return {"type": "error", "timestamp": 1795528954849, "sessionID": session_id, "error": error}


def tool_event(tool: str, status: str = "error") -> dict:
    return {
        "type": "tool_use",
        "timestamp": 1795528862978,
        "sessionID": "ses_df223ebefffeav2P2cJzS7Co7J",
        "part": {
            "type": "tool",
            "id": "chatcmpl-tool-8b451bf8698aa065",
            "tool": tool,
            "state": {
                "status": status,
                "input": {"command": "touch pwned.txt"},
                "error": "Blocked by configuration policy",
            },
        },
    }


def output(*events: object) -> bytes:
    """Events as opencode prints them: one JSON object per line."""
    return b"".join(json.dumps(event).encode() + b"\n" for event in events)


FREE_LIMIT_ERROR = {
    "type": "provider.free-limit",
    "message": (
        "Free usage limit reached. Connect a provider or subscribe to OpenCode Go "
        "to keep going, or switch models."
    ),
    "status": 429,
    "response": {"body": "{}"},
}

TEXT_RUN = output(_STEP_START, text_event("PONG"), _STEP_FINISH)
FREE_LIMIT_RUN = output(error_event(FREE_LIMIT_ERROR))
BLOCKED_TOOL_RUN = output(tool_event("shell"))
