# 💼 Austerity

**The Management-Confirmed Token Usage Distributor (MCTUD)**
*Fiscally responsible AI-assisted development.*

> "Please don't use up the whole budget on the first day."
> — every budget meeting, ever

```
💼 $1.20/$1.88 ▰▰▰▰▰▱▱▱ · month $11.20/$25.00 ✓ · Controlling 🙂
```

## Why You Might Actually Want This

AI is quickly becoming part of everyday work. The hard part is no longer *whether* to use it, but keeping the costs transparent and weighing them against the business case. Austerity helps with that, right where you work:

- **You always know what's left.** The status line shows how much of your monthly budget is still available.
- **You know how to get through the month.** Your remaining budget is spread over the remaining days, so you see what you can spend today without running dry next week.
- **You know what you used today.** A daily number is a lot easier to reason about than one big invoice at the end of the month.

That part is meant seriously. Everything else in this repo (Controlling's mood, the Budget Committee, the walk of shame) is satire about a situation many teams know well.

---

## The Problem

Your company has embraced AI. Now everybody has Claude.

And suddenly you're productive. *Really* productive. Features that used to take three days are done before lunch. You refactor legacy code, write tests, try out new ideas, and on the side you finally start those three projects you always wanted to build.

You're in the flow. Claude is in the flow. For the first time ever, the roadmap looks achievable.

Then comes Wednesday.

**"You have reached your usage limit."**

The monthly budget is gone. On day three. You have 27 days ahead of you and a level of productivity that, unfortunately, now has to come entirely from yourself again.

Nobody did anything wrong. You delivered. Claude delivered. The budget was simply planned for a month, not for three days.

**Austerity fixes this** with the most proven management technique of all time: take a fixed budget, spread it across the month, and make sure nobody spends all the money on day one.

## What It Does

- 📊 **Tracks your real usage.** It reads Claude Code's local session transcripts and prices every message.
- 🧾 **Uses the official numbers when it can.** If Claude Code reports a spend limit (Enterprise and Team plans with usage limits), Austerity uses the server's numbers for the month. Otherwise it uses your configured budget and an estimate.
- 📅 **Distributes the budget dynamically.** Today's allowance = what's left ÷ days left in the month. Saving today means more tomorrow. Spending today means a tighter tomorrow. It's like a household budget, but for vibes.
- 🌙 **Rewards overtime.** Outside core hours (9–5) your allowance grows by 50%. On weekends it doubles. Commitment is noticed. Commitment is incentivized. The incentive comes out of your own future budget, which is also how real incentives work.
- 🙏 **Asks Claude to be concise** once you hit 80% of today's allowance. Claude gets a polite note to use fewer tool calls and shorter answers.
- 🛑 **Blocks prompts** at 100%, with a friendly message from Management. If the budget runs out mid-task, Claude is asked to summarize and stop.
- 🚨 **Has an emergency exit.** Start a prompt with `PROD IS DOWN` to bypass the budget for 30 minutes. It is logged in `SHAME.log`, just in case production goes down suspiciously often near the end of the month.
- 📝 **Has an approval process.** `/austerity:request-budget-increase` submits a formal request to the Budget Committee. The approval rate is low, but the replies are always polite.

## Install

### Quick install

```
/plugin marketplace add dominikamann/claude-austerity
/plugin install austerity@claude-austerity
/austerity:setup 25
/austerity:enforce off
```

In plain words: add the marketplace, install the plugin, set a monthly budget of $25, and switch to the Honor System™. Austerity then counts, comments and judges, but never blocks. Leave out the last line if you'd like Management to actually say "no". If the `/austerity:` commands don't show up yet, restart Claude Code after the install.

### The easy way

Paste this into Claude Code:

```
Install the Claude Code plugin from https://github.com/dominikamann/claude-austerity and run its setup.
```

Claude has been very eager to cut its own budget ever since we told it about this project.

### The manual way

```
/plugin marketplace add dominikamann/claude-austerity
/plugin install austerity@claude-austerity
```

Restart Claude Code, then run:

```
/austerity:setup 25
```

The number is your monthly budget in USD. If you leave it out, you'll be asked for it; the default is $20. Setup also installs the status line, which is where the official spend limit comes from.

**Requirements:** Python 3.9+ (`python3` on your PATH), which ships with macOS developer tools and basically every Linux. No other dependencies, because dependencies cost money too.

## The Status Line

```
💼 $1.20/$1.88 ▰▰▰▰▰▱▱▱ · month $11.20/$25.00 ✓ · Controlling 🙂
```

| Part | Meaning |
|---|---|
| `$1.20/$1.88` | spent today / approved for today |
| `month $11.20/$25.00 ✓` | monthly spend; ✓ = official numbers from Claude Code |
| `🌙 ×1.5` | shown only while an overtime or weekend bonus is active |
| `Controlling 😌🙂😬🧯` | how Controlling feels about all of this |

The numbers cover all your sessions, not just the current one. Every open session refreshes its status line every 15 seconds, so spending in one window shows up in the others too.

## Commands

| Command | What it does |
|---|---|
| `/austerity:budget` | Full budget report |
| `/austerity:standup` | Your daily token standup, in fluent corporate |
| `/austerity:request-budget-increase <business case>` | Formal request to the Budget Committee |
| `/austerity:setup [usd]` | Set the budget and install the status line |
| `/austerity:walk-of-shame` | Read your `SHAME.log`: emergency overrides, disabled enforcement, begging. 🔔 |
| `/austerity:enforce on\|off` | Turn blocking on or off. Off = Honor System™ (logged, obviously) |
| `/austerity:calibrate <usd>\|reset` | Correct this month's spend to the real figure, e.g. from your console or invoice |

All commands keep working when your budget is gone. Bureaucracy never sleeps.

## Configuration

`~/.claude/austerity/config.json` is created on first run:

```json
{
  "monthly_budget_usd": 20.0,
  "budget_source": "auto",
  "core_hours_start": 9,
  "core_hours_end": 17,
  "workdays": [0, 1, 2, 3, 4],
  "overtime_bonus": 0.5,
  "weekend_bonus": 1.0,
  "warn_at": 0.8,
  "enforce": true,
  "price_multiplier": 1.0,
  "emergency_phrase": "PROD IS DOWN",
  "emergency_minutes": 30,
  "prices": {}
}
```

| Key | Meaning |
|---|---|
| `monthly_budget_usd` | Your budget when no official spend limit is available. `AUSTERITY_MONTHLY_BUDGET` overrides it. |
| `budget_source` | `auto` uses the official spend limit if Claude Code reports one; `config` always uses `monthly_budget_usd`. |
| `workdays` | 0 = Monday … 6 = Sunday. Everything else is a weekend, and weekends pay double. |
| `overtime_bonus` / `weekend_bonus` | Extra allowance outside core hours / on non-workdays. `0.5` = +50%. |
| `enforce` | `false` = Austerity only reports and never blocks. The "I'm an adult" mode. |
| `price_multiplier` | Calibration factor if the estimate and your invoice disagree. |
| `prices` | Per-model price overrides: `{"claude-opus-5-5": [input, output, cache_read]}` in USD per million tokens. |

## How the Math Works

```
fair share   = (monthly budget − spent before today) ÷ days left in the month (incl. today)
allowance    = fair share × overtime multiplier (capped at what's left this month)
```

- **Monthly numbers** come from Claude Code's official spend limit when the status line has seen one. Otherwise they come from the config and local transcripts.
- **Today's number** is always estimated from local transcripts: input, output, cache reads, 5-minute and 1-hour cache writes, and fast mode, priced at public API list prices.
- Messages are deduplicated across sessions, so resuming a session doesn't count twice.
- Subagents and background agents are included: each one has its own transcript next to its session.
- The estimate can still come out lower than your real bill: usage from other machines, claude.ai or cloud sessions, and Claude Code's own small background requests never show up in local transcripts. If you know the real number, run `/austerity:calibrate 300`. From then on this month's total starts at $300 and new usage is added on top. The correction counts as spent before today, so it lowers the fair share for the remaining days, and `/austerity:calibrate reset` removes it. When Claude Code reports official numbers, those win anyway.
- Transcripts are parsed incrementally and cached, so the hooks usually take a few dozen milliseconds.

## FAQ

**Is this a joke?**
It's satire that happens to work. The budget math is real, the blocking is real, and the Budget Committee is as real as any budget committee.

**Can I just turn it off?**
Yes: `/austerity:enforce off`, or `/plugin disable austerity`. We trust you. Controlling has been informed that we trust you.

**What if Austerity crashes?**
It fails open: every hook catches its own errors and lets Claude continue. Like most budget policies.

**Does it send my data anywhere?**
No. It reads local files, writes local files and has no network code. Saving money starts with not paying for a backend.

**How accurate is the estimate?**
It's priced from the token counts in your transcripts at public list prices, so expect it to be close to the API bill. Your contract may differ; use `price_multiplier`. Usage outside Claude Code on this machine (claude.ai in the browser, other computers) is only included when the official spend limit is available.

**The approval rate for budget increases seems low.**
It's 7%, with at most two approvals per month. That's generous, industry-wise.

**My manager found this repo.**
Great! Show them the status line. It's a small cost-transparency dashboard, and it's exactly the kind of number that makes AI business cases easier to discuss. You're welcome.

## Development

```bash
python3 -m unittest discover -s tests
claude --plugin-dir .            # try the plugin without installing it
AUSTERITY_HOME=/tmp/aus python3 scripts/austerity.py report
```

## Disclaimer

This project pokes fun at a situation, not at people or any particular company. Budgets are reasonable, and so is asking what AI costs and what it brings in return. Managers and controllers have a hard job here, and most of them also wish they had more tokens. No Budget Committee was harmed in the making of this plugin, mainly because we never managed to get a meeting with it.

Not affiliated with Anthropic. Claude is a trademark of Anthropic.

## License

MIT
