---
description: Turn budget enforcement on or off (off = Honor System™)
argument-hint: [on|off]
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py *)
---

The user wants to change budget enforcement. Their input: $ARGUMENTS

- If the input means "on" (on, an, true, ja, 1, …), run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py enforce on`.
- If it means "off" (off, aus, false, nein, 0, …), run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py enforce off`.
- If it's empty or unclear, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py enforce` to show the current state.

Show the script's output to the user, translated into the language the user writes in. Add nothing else.
