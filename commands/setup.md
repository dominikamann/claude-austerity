---
description: Set your monthly budget and install the Austerity status line
argument-hint: [monthly budget in USD, default 20]
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py *)
---

Set up Austerity for the user:

1. Monthly budget: if `$ARGUMENTS` is a number, use it. Otherwise ask the user for their monthly budget in USD and suggest 20. Then run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py set-budget <amount>`.
2. Status line: run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py install-statusline`. If the output starts with `EXISTING_STATUSLINE`, show the user their current status line and ask whether to replace it. Only if they agree, run it again with `--force`.
3. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py report` and show the output in a code block.

Finish with one sentence: the status line appears after the next message, and the config lives in `~/.claude/austerity/config.json` (core hours, overtime bonus, emergency phrase).
