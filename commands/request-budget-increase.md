---
description: Submit a formal request for more tokens to the Budget Committee
argument-hint: <business case>
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py *)
---

The user submitted this business case: $ARGUMENTS

The Budget Committee has decided:

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py request-increase`

Write the committee's reply as a short, formal corporate letter (at most 5 sentences) that announces the decision above and refers to the business case. Keep the decision and all numbers exactly as given. The tone is dry, polite and self-aware corporate satire: the joke is on the process, never on the user, their manager or their company. If no business case was given, note that the form was submitted without one. Write in the language the user writes in. Open with a gender-neutral salutation: "Dear Applicant," in English, "Sehr geehrte antragstellende Person," in German, or the equivalent in other languages. Sign as "The Budget Committee" (in German: "Die Budget-Kommission").
