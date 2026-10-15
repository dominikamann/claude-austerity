---
description: Daily token standup, in fluent corporate
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py *)
---

Today's numbers:

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py standup-facts`

Write the user's daily standup from these numbers, in the language the user writes in. Use the classic three parts (yesterday, today, blockers) plus one closing line from Controlling that matches its mood. At most 8 short lines, no intro, no outro.

Tone: overly earnest corporate speak that takes a token budget far too seriously (KPIs, alignment, runway, synergies, "circling back"). Keep every number exactly as given. The joke is on the process and the jargon, never on the user, their manager or their company. Vary the phrasing each time.

End with this line, translated if needed: "This standup was generated with tokens. They have been deducted from your budget."
