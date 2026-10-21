---
description: Correct this month's spend to the real figure (e.g. from your invoice or console)
argument-hint: <actual spend this month in USD> | reset
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py *)
---

The user wants to correct this month's spend. Their input: $ARGUMENTS

- If the input contains an amount, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py calibrate <amount>` with the plain number (e.g. `300` or `300.50`, no currency sign, dot as decimal separator).
- If it means "reset" (reset, zurücksetzen, remove, …), run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py calibrate reset`.
- If it's empty, ask the user how much they have really spent this month, then run the command.

Show the script's output to the user, translated into the language the user writes in. Add nothing else.
