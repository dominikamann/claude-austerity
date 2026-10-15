---
description: Submit a formal request for more tokens to the Budget Committee
argument-hint: <business case>
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py *)
---

The user's business case: $ARGUMENTS

The Budget Committee has decided:

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/austerity.py request-increase`

Write the committee's reply as a short, punchy formal letter (3–5 sentences) in the language the user writes in. Translate the decision word too (e.g. ABGELEHNT / IN PRÜFUNG / GENEHMIGT).

- Build the letter around the **Reason** above. It is the punchline, so phrase it well and don't water it down. Keep every number exactly as given; skip the request statistics unless they make the joke better.
- Mention the business case only if it adds to the joke, for example by quoting a phrase from it with mock seriousness. If none was given, you may remark that submitting a request without a business case shows remarkable confidence.
- Style: exaggerated, earnest corporate speak with the occasional dry aside. Vary the structure every time; don't start every letter the same way after the salutation.
- The goal is to make a developer laugh. The joke is on corporate processes, never on the user, their manager or their company.
- Open with a gender-neutral salutation: "Dear Applicant," in English, "Sehr geehrte antragstellende Person," in German, or the equivalent in other languages. Sign as "The Budget Committee" (in German: "Die Budget-Kommission"). You may add a P.S. if it's funny.
