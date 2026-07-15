"""
A plugin to fetch the current system time.
"""

import time

PLUGIN_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current local system time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]


def get_current_time() -> str:
    return f"The current system time is {time.strftime('%Y-%m-%d %H:%M:%S')}"
