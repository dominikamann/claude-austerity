#!/usr/bin/env python3
"""Austerity: the Management-Confirmed Token Usage Distributor (MCTUD).

Reads Claude Code's local session transcripts, estimates what they cost and
spreads a monthly budget evenly across the remaining days of the month.
Overtime and weekends unlock a bonus, because of course they do.

Standard library only. Python 3.9+. Fails open: if anything in here breaks,
Claude keeps working. Like most budget policies.
"""

import calendar
import datetime as dt
import json
import os
import random
import sys
import tempfile

VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
PROJECTS_DIR = os.path.join(CLAUDE_DIR, "projects")
HOME = os.environ.get("AUSTERITY_HOME") or os.path.join(CLAUDE_DIR, "austerity")
CONFIG_PATH = os.path.join(HOME, "config.json")
LEDGER_PATH = os.path.join(HOME, "ledger.json")
CACHE_PATH = os.path.join(HOME, "cache.json")
SHAME_LOG = os.path.join(HOME, "SHAME.log")
OFFICIAL_PATH = os.path.join(HOME, "official.json")
# Stable copy for the status line (plugin paths change with every update).
STATUSLINE_COPY = os.path.join(HOME, "austerity.py")
SETTINGS_PATH = os.path.join(CLAUDE_DIR, "settings.json")

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "monthly_budget_usd": 20.0,
    # "auto": use the official spend limit when Claude Code reports one
    # (seen by the status line), otherwise monthly_budget_usd.
    # "config": always use monthly_budget_usd.
    "budget_source": "auto",
    # Core hours, local time. Everything outside counts as overtime.
    "core_hours_start": 9,
    "core_hours_end": 17,
    # 0 = Monday ... 6 = Sunday
    "workdays": [0, 1, 2, 3, 4],
    # Extra allowance on top of the fair daily share.
    "overtime_bonus": 0.5,
    "weekend_bonus": 1.0,
    # Start asking Claude to be brief at this share of today's allowance.
    "warn_at": 0.8,
    # false = report only, never block.
    "enforce": True,
    # Calibration factor if your invoice disagrees with the estimate.
    "price_multiplier": 1.0,
    # Start a prompt with this phrase to bypass the budget (gets logged).
    "emergency_phrase": "PROD IS DOWN",
    "emergency_minutes": 30,
    # Optional per-model overrides, same shape as PRICES below.
    "prices": {},
}

# USD per million tokens: input, output, cache read.
# Cache writes are billed at 1.25x (5 min TTL) or 2x (1 h TTL) the input price.
# Matched by longest prefix of the model id.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-mythos-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-mythos": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4": (3.0, 15.0, 0.30),
    "claude-haiku-4": (1.0, 5.0, 0.10),
    "claude-3-5-haiku": (0.8, 4.0, 0.08),
}
FALLBACK_PRICE = (5.0, 25.0, 0.50)
FAST_MODE_MULTIPLIER = 2.0


def ensure_home():
    os.makedirs(HOME, exist_ok=True)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    ensure_home()
    fd, tmp = tempfile.mkstemp(dir=HOME, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if not os.path.exists(CONFIG_PATH):
        write_json(CONFIG_PATH, DEFAULT_CONFIG)
    cfg.update(read_json(CONFIG_PATH, {}))
    env_budget = os.environ.get("AUSTERITY_MONTHLY_BUDGET")
    if env_budget:
        cfg["monthly_budget_usd"] = float(env_budget)
    return cfg


def price_for(model, overrides=None):
    table = dict(PRICES)
    for k, v in (overrides or {}).items():
        table[k] = tuple(v)
    best = None
    for prefix in table:
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return table[best] if best else FALLBACK_PRICE


def cost_of(model, usage, overrides=None):
    p_in, p_out, p_read = price_for(model, overrides)
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    read = usage.get("cache_read_input_tokens") or 0
    split = usage.get("cache_creation") or {}
    write_1h = split.get("ephemeral_1h_input_tokens") or 0
    write_5m = split.get("ephemeral_5m_input_tokens")
    if write_5m is None:
        write_5m = (usage.get("cache_creation_input_tokens") or 0) - write_1h
    cost = (
        inp * p_in
        + out * p_out
        + read * p_read
        + write_5m * p_in * 1.25
        + write_1h * p_in * 2.0
    ) / 1_000_000
    if usage.get("speed") == "fast":
        cost *= FAST_MODE_MULTIPLIER
    return cost


# --------------------------------------------------------------------------
# Usage scanning (incremental, cached)
# --------------------------------------------------------------------------


def parse_ts(value):
    """ISO timestamp from a transcript -> local aware datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value).astimezone()


def parse_lines(lines, month_key, overrides):
    """Yield (dedup_key, day, cost) for assistant messages in the given month."""
    for raw in lines:
        if '"usage"' not in raw:
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if d.get("type") != "assistant":
            continue
        msg = d.get("message") or {}
        usage = msg.get("usage")
        model = msg.get("model") or ""
        if not usage or model.startswith("<"):
            continue
        try:
            ts = parse_ts(d["timestamp"])
        except (KeyError, ValueError):
            continue
        day = ts.strftime("%Y-%m-%d")
        if not day.startswith(month_key):
            continue
        key = "%s:%s" % (msg.get("id"), d.get("requestId"))
        yield key, day, cost_of(model, usage, overrides)


def iter_transcripts(since_epoch):
    if not os.path.isdir(PROJECTS_DIR):
        return
    for root, _dirs, files in os.walk(PROJECTS_DIR):
        for name in files:
            if name.endswith(".jsonl"):
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if st.st_mtime >= since_epoch:
                    yield path, st


def scan_usage(now, overrides=None, max_age_s=0):
    """Return {day: cost_usd} for the month of `now`.

    Files are parsed incrementally from the last known offset. With max_age_s,
    a recent result is reused without touching the transcripts at all.
    """
    month_key = now.strftime("%Y-%m")
    cache = read_json(CACHE_PATH, {})
    if cache.get("version") != 2 or cache.get("month") != month_key:
        cache = {"version": 2, "month": month_key, "files": {}, "days": {}, "at": 0}

    if max_age_s and now.timestamp() - cache.get("at", 0) < max_age_s:
        return cache.get("days", {})

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    files = cache["files"]
    seen = set()
    for path, st in iter_transcripts(month_start.timestamp()):
        seen.add(path)
        entry = files.get(path)
        if entry and entry["size"] == st.st_size and entry["mtime"] == st.st_mtime:
            continue
        if not entry or st.st_size < entry["size"]:
            entry = {"offset": 0, "msgs": {}}
        try:
            with open(path, "rb") as f:
                f.seek(entry["offset"])
                chunk = f.read()
        except OSError:
            continue
        # Keep a trailing partial line for the next run.
        complete, sep, _partial = chunk.rpartition(b"\n")
        lines = complete.decode("utf-8", errors="replace").split("\n")
        msgs = entry["msgs"]
        for key, day, cost in parse_lines(lines, month_key, overrides):
            # Streaming writes one line per content block with the same id;
            # keep the most expensive copy.
            if key not in msgs or cost > msgs[key][1]:
                msgs[key] = [day, cost]
        entry["offset"] += len(complete) + len(sep)
        entry["size"] = st.st_size
        entry["mtime"] = st.st_mtime
        files[path] = entry

    for path in list(files):
        if path not in seen:
            del files[path]

    # Resumed sessions copy history into new files: dedupe across files too.
    merged = {}
    for entry in files.values():
        for key, (day, cost) in entry["msgs"].items():
            if key not in merged or cost > merged[key][1]:
                merged[key] = (day, cost)
    days = {}
    for day, cost in merged.values():
        days[day] = days.get(day, 0.0) + cost

    cache["days"] = days
    cache["at"] = now.timestamp()
    try:
        write_json(CACHE_PATH, cache)
    except OSError:
        pass
    return days


# --------------------------------------------------------------------------
# Ledger (approved increases, incidents, overrides)
# --------------------------------------------------------------------------


def load_ledger():
    return read_json(LEDGER_PATH, {"months": {}, "override_until": None})


def month_book(ledger, now):
    return ledger["months"].setdefault(
        now.strftime("%Y-%m"),
        {"approved_usd": 0.0, "requests": 0, "approvals": 0, "incidents": 0},
    )


def override_active(ledger, now):
    until = ledger.get("override_until")
    return bool(until) and now.timestamp() < until


# --------------------------------------------------------------------------
# Official spend limit (reported to the status line by Claude Code)
# --------------------------------------------------------------------------


def record_official(now, statusline_input):
    """Remember rate_limits.spend_limit from the status line payload."""
    limits = (statusline_input or {}).get("rate_limits") or {}
    spend = limits.get("spend_limit") or {}
    used, limit = spend.get("used_usd"), spend.get("limit_usd")
    if not isinstance(used, (int, float)) or not isinstance(limit, (int, float)) or limit <= 0:
        return
    data = {"month": now.strftime("%Y-%m"), "used_usd": float(used),
            "limit_usd": float(limit), "at": now.timestamp()}
    old = read_json(OFFICIAL_PATH, {})
    unchanged = all(old.get(k) == data[k] for k in ("month", "used_usd", "limit_usd"))
    if unchanged and now.timestamp() - old.get("at", 0) < 300:
        return
    write_json(OFFICIAL_PATH, data)


def load_official(now, cfg):
    if cfg.get("budget_source") == "config":
        return None
    data = read_json(OFFICIAL_PATH, None)
    if not data or data.get("month") != now.strftime("%Y-%m"):
        return None
    if now.timestamp() - data.get("at", 0) > 24 * 3600:
        return None
    return data


# --------------------------------------------------------------------------
# Budget math
# --------------------------------------------------------------------------


def overtime(now, cfg):
    """Return (multiplier, label) for the current moment."""
    if now.weekday() not in cfg["workdays"]:
        return 1.0 + cfg["weekend_bonus"], "weekend bonus"
    if not (cfg["core_hours_start"] <= now.hour < cfg["core_hours_end"]):
        return 1.0 + cfg["overtime_bonus"], "overtime bonus"
    return 1.0, None


def budget_status(now, cfg, days, ledger, official=None):
    book = month_book(ledger, now)
    today = now.strftime("%Y-%m-%d")
    mult = cfg["price_multiplier"]
    spent_today = days.get(today, 0.0) * mult
    if official:
        # The server knows the real numbers for the month; today's share
        # still comes from the local transcripts.
        monthly = official["limit_usd"] + book["approved_usd"]
        spent_month = official["used_usd"]
        source = "official"
    else:
        monthly = cfg["monthly_budget_usd"] + book["approved_usd"]
        spent_month = sum(days.values()) * mult
        source = "estimate"
    left_before_today = max(0.0, monthly - max(0.0, spent_month - spent_today))

    days_in_month = calendar.monthrange(now.year, now.month)[1]
    remaining_days = days_in_month - now.day + 1
    fair_share = left_before_today / remaining_days
    multiplier, bonus_label = overtime(now, cfg)
    allowance = min(fair_share * multiplier, left_before_today)

    ratio = spent_today / allowance if allowance > 0 else float("inf")
    if spent_month >= monthly:
        state = "bankrupt"
    elif ratio >= 1.0:
        state = "exhausted"
    elif ratio >= cfg["warn_at"]:
        state = "warn"
    else:
        state = "ok"

    next_bonus = None
    if state == "exhausted" and multiplier == 1.0:
        next_bonus = cfg["core_hours_end"]

    return {
        "state": state,
        "source": source,
        "official_at": official["at"] if official else None,
        "today": today,
        "spent_today": spent_today,
        "allowance": allowance,
        "fair_share": fair_share,
        "ratio": ratio,
        "spent_month": spent_month,
        "monthly": monthly,
        "approved_bonus": book["approved_usd"],
        "remaining_days": remaining_days,
        "multiplier": multiplier,
        "bonus_label": bonus_label,
        "next_bonus_hour": next_bonus,
        "incidents": book["incidents"],
        "override": override_active(ledger, now),
    }


def current_status(max_age_s=0, now=None):
    now = now or dt.datetime.now().astimezone()
    cfg = load_config()
    days = scan_usage(now, cfg.get("prices"), max_age_s=max_age_s)
    ledger = load_ledger()
    official = load_official(now, cfg)
    return now, cfg, ledger, budget_status(now, cfg, days, ledger, official)


# --------------------------------------------------------------------------
# Copy department
# --------------------------------------------------------------------------


def money(x):
    return "$%.2f" % x


def pct(ratio):
    return 999 if ratio == float("inf") else min(999, int(ratio * 100))


def bar(ratio, width=10):
    filled = max(0, min(width, int(round(min(ratio, 1.0) * width))))
    return "▰" * filled + "▱" * (width - filled)


MOOD = [
    (0.5, "😌", "relaxed"),
    (0.8, "🙂", "cautiously optimistic"),
    (1.0, "😬", "reviewing spreadsheets"),
    (float("inf"), "🧯", "in a meeting about this"),
]


def mood(ratio):
    for limit, emoji, text in MOOD:
        if ratio < limit:
            return emoji, text
    return MOOD[-1][1], MOOD[-1][2]


BLOCK_HEADLINES = [
    "Your request has been forwarded to Management for approval.",
    "Thank you for your enthusiasm. It has been noted.",
    "This prompt exceeds today's approved innovation volume.",
    "We have identified a synergy between you and a break.",
    "Your prompt has been added to the backlog. Priority: someday.",
]

BLOCK_HINTS = [
    "Expected processing time: 3–5 business days.",
    "Pro tip: a coffee costs less than a context window.",
    "Have you considered thinking about it yourself first? (Free, no tokens.)",
    "Today's budget recovers automatically at midnight. Like your motivation.",
    "Rubber ducks are fully pre-approved and require no tokens.",
]

# Reasons for /austerity:request-budget-increase. Claude builds a letter
# around the one that is drawn, so every reply reads differently.
REJECTIONS = [
    "You are currently far too productive. To protect the organization from uncontrolled velocity, we cannot release additional tokens at this time.",
    "We were unable to follow your business case. It is too optimistic, too well-founded and contains no buzzwords at all, which made the committee suspicious.",
    "Your business case shows a positive ROI. Our approval process is not designed for that. Please resubmit with a negative ROI so it can be approved like every other project.",
    "Your output has exceeded the organization's capacity to review it. Please slow down so code review can catch up (estimated: Q3 of next year).",
    "The Budget Committee approved your request, but the Committee for Reviewing Budget Committee Decisions did not.",
    "Our AI-based approval tool ran out of tokens while evaluating your request.",
    "All available tokens are reserved for the upcoming AI strategy presentation, which explains how important it is that everyone uses AI more.",
    "Your request was submitted outside the official request window (every second Tuesday, 09:00–09:05, leap years only).",
    "You have already delivered this quarter's roadmap. Further productivity would create expectations the organization cannot sustain long-term.",
    "Your business case is missing the mandatory slide with a rocket on it.",
    "We opened your business case in Excel. Excel crashed. The committee is treating this as a vote against.",
    "Unfortunately, \"it would make me faster\" is not a recognized business reason. \"It would make us look innovative in the press release\" would have been.",
    "The committee was so impressed by your request that it scheduled a workshop to discuss the impression. Results are expected next fiscal year.",
    "If you finish everything this month, there will be nothing left for next month's OKRs. Please think of the OKRs.",
    "The request does not reference a cost center, and the cost center does not reference a request. The committee cannot resolve this paradox.",
    "Granting more tokens would make it difficult to explain to the board why we are also hiring more people.",
    "Your request was reviewed with great care, approved in principle, and denied in practice.",
    "The current savings initiative is going so well that it has its own budget, which has unfortunately been used up.",
]

PENDING = [
    "Your request has been forwarded to the Budget Committee, which meets on the 32nd of each month.",
    "Your request is now in review. Current queue position: 4,182. Estimated waiting time: yes.",
    "Your request requires an alignment meeting with 14 stakeholders. The first slot that works for everyone is after the next reorg.",
    "Your request has been converted into a ticket. Status: Backlog. Priority: Medium, which is corporate for 'never'.",
    "Your request needs a signature from a stakeholder nobody has seen since the last reorg. The search is ongoing.",
    "Your request has been escalated, de-escalated, and re-escalated. It is currently in an escalation loop and doing well.",
]

APPROVALS = [
    "Approved due to a clerical error. Please don't tell anyone.",
    "Approved, because the committee's quarterly target included 'approve at least one thing'.",
    "Approved. The committee was in a good mood after the team event. This will not happen again.",
    "Approved, as a one-time exception that will be cited as precedent forever.",
]

WARNINGS = [
    "Friendly reminder from Controlling: {pct}% of today's tokens are already productive.",
    "{pct}% used. This is a great moment to ask yourself: do I really need Claude for this, or do I just enjoy its company?",
    "{pct}% of today's budget used. Claude has been asked to keep it short. Claude has agreed. Briefly.",
    "{pct}% used. Please keep all further prompts lean, agile and under budget.",
    "Heads-up: {pct}% of today's runway is behind us. Fasten your seatbelts and close unused tabs.",
]

GREETINGS_CORE = [
    "Welcome back. Your token allowance has been pre-approved and is ready for responsible use.",
    "Good to see you. Today's productivity has been budgeted in advance.",
    "Session opened. Controlling has been notified and wishes you a fiscally sound day.",
]

GREETINGS_OVERTIME = [
    "Working after hours? Your commitment has been noted and rewarded.",
    "Overtime detected. The extra tokens are our way of saying 'please go home'.",
    "Burning the midnight oil? Burning extra tokens is now officially approved.",
]

GREETINGS_WEEKEND = [
    "Weekend shift detected. Double tokens. Single life.",
    "Working on a weekend? Management will mention this in your review. Positively, probably.",
    "Welcome to the weekend shift. The budget is doubled, the coffee is not.",
]

GREETINGS_BROKE = [
    "Welcome back. Your budget for today has already been fully invested in the future.",
    "Session opened in read-only mode for your wallet. Commands still work, ambitions do not.",
]

REPORT_FOOTERS = [
    "This report was produced at zero token cost. You're welcome.",
    "No tokens were harmed in the making of this report.",
    "Please print this report and file it in the appropriate folder.",
    "Remember: every token saved today is a token saved today.",
]

STANDUP_YESTERDAY = [
    "leveraged AI-driven synergies to move the needle",
    "aligned cross-functionally with the language model",
    "drove token-efficient outcomes in a fast-paced environment",
    "explored several paradigm shifts, some of them on purpose",
]

STANDUP_BLOCKERS = {
    "ok": "No blockers. Budget is healthy. Suspiciously healthy.",
    "warn": "Mild blocker: the token runway is shorter than the sprint.",
    "exhausted": "Blocker: today's tokens have been fully monetized.",
    "bankrupt": "Blocker: the monthly budget has achieved its final form (zero).",
}


def format_report(s, cfg):
    emoji, mood_text = mood(s["ratio"])
    lines = [
        "AUSTERITY · Token Usage Report · %s" % s["today"],
        "",
        "Today       %s / %s  %s %d%%"
        % (money(s["spent_today"]), money(s["allowance"]), bar(s["ratio"]), pct(s["ratio"])),
        "This month  %s / %s" % (money(s["spent_month"]), money(s["monthly"])),
        "Fair share  %s per day for the remaining %d day(s)"
        % (money(s["fair_share"]), s["remaining_days"]),
    ]
    if s["bonus_label"]:
        lines.append("Bonus       ×%.1f %s active. Dedication pays. Literally."
                     % (s["multiplier"], s["bonus_label"]))
    else:
        lines.append("Bonus       none (core hours). Overtime unlocks ×%.1f after %d:00. Just saying."
                     % (1 + cfg["overtime_bonus"], cfg["core_hours_end"]))
    if s["approved_bonus"]:
        lines.append("Approved    +%s via official request process" % money(s["approved_bonus"]))
    if s["incidents"]:
        lines.append("Incidents   %d emergency override(s) this month" % s["incidents"])
    lines += [
        "Controlling %s %s" % (emoji, mood_text),
        "",
    ]
    lines.append(random.choice(REPORT_FOOTERS))
    lines.append("")
    if s["source"] == "official":
        age = max(0, int((dt.datetime.now().timestamp() - s["official_at"]) / 60))
        lines.append("Month: official spend limit reported by Claude Code (%d min ago)." % age)
        lines.append("Today: estimated from local transcripts at API list prices.")
    else:
        lines.append("Estimated from local transcripts at API list prices.")
        lines.append("Official numbers appear once the status line sees a spend limit (/austerity:setup).")
    return "\n".join(lines)


def block_message(s, cfg):
    rng = random.Random(s["today"] + str(int(s["spent_today"] * 100)))
    lines = ["💼 " + rng.choice(BLOCK_HEADLINES), ""]
    if s["state"] == "bankrupt":
        lines.append("Monthly budget used: %s of %s. See you next month."
                     % (money(s["spent_month"]), money(s["monthly"])))
    else:
        lines.append("Today: %s of %s approved." % (money(s["spent_today"]), money(s["allowance"])))
        if s["next_bonus_hour"] is not None:
            lines.append("Good news: overtime starts at %d:00 and unlocks ×%.1f budget."
                         % (s["next_bonus_hour"], 1 + cfg["overtime_bonus"]))
        else:
            lines.append("Tomorrow's allowance is recalculated at midnight.")
    lines += [
        rng.choice(BLOCK_HINTS),
        "",
        "Options: /austerity:request-budget-increase · start your prompt with \"%s\" (logged)"
        % cfg["emergency_phrase"],
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Hooks
# --------------------------------------------------------------------------


def read_hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))


def log_shame(now, what):
    ensure_home()
    with open(SHAME_LOG, "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (now.strftime("%Y-%m-%d %H:%M"), what))


def hook_prompt():
    data = read_hook_input()
    prompt = (data.get("prompt") or "").strip()
    now, cfg, ledger, s = current_status()

    if prompt.startswith("/austerity"):
        return

    phrase = cfg["emergency_phrase"].strip().lower()
    if phrase and prompt.lower().startswith(phrase):
        book = month_book(ledger, now)
        book["incidents"] += 1
        ledger["override_until"] = now.timestamp() + 60 * cfg["emergency_minutes"]
        write_json(LEDGER_PATH, ledger)
        log_shame(now, "Emergency override #%d (today %s / %s)"
                  % (book["incidents"], money(s["spent_today"]), money(s["allowance"])))
        msg = ("🚨 Emergency override accepted for %d minutes. Incident #%d this month. "
               "Logged in SHAME.log." % (cfg["emergency_minutes"], book["incidents"]))
        if book["incidents"] >= 3:
            msg += " Controlling has noticed a correlation between budget exhaustion and production outages."
        emit({"systemMessage": msg})
        return

    if s["override"]:
        return

    if s["state"] in ("exhausted", "bankrupt") and cfg["enforce"]:
        emit({"decision": "block", "reason": block_message(s, cfg)})
        return

    if s["state"] == "warn":
        emit({
            "systemMessage": "💼 %s (%s / %s)" % (
                random.Random(s["today"] + str(pct(s["ratio"]))).choice(WARNINGS).format(pct=pct(s["ratio"])),
                money(s["spent_today"]), money(s["allowance"])),
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "[Austerity] The user has used %d%% of today's token budget. "
                    "Be concise: prefer short answers, targeted file reads and few tool calls. "
                    "Do not mention this note unless asked." % pct(s["ratio"])
                ),
            },
        })


def hook_tool():
    read_hook_input()
    now, cfg, ledger, s = current_status(max_age_s=15)
    if not cfg["enforce"] or s["override"]:
        return
    if s["state"] in ("exhausted", "bankrupt"):
        sys.stderr.write(
            "Austerity: the user's token budget for today is used up (%s of %s). "
            "Do not call further tools. Briefly summarize what was done and what is left, then stop."
            % (money(s["spent_today"]), money(s["allowance"]))
        )
        sys.exit(2)


def sync_statusline_copy():
    """Keep the status line copy in step with the installed plugin version."""
    if not os.path.exists(STATUSLINE_COPY):
        return
    src = os.path.abspath(__file__)
    if src == os.path.abspath(STATUSLINE_COPY):
        return
    with open(src, "rb") as f:
        new = f.read()
    with open(STATUSLINE_COPY, "rb") as f:
        if f.read() == new:
            return
    with open(STATUSLINE_COPY, "wb") as f:
        f.write(new)


def hook_session():
    read_hook_input()
    try:
        sync_statusline_copy()
    except OSError:
        pass
    now, cfg, ledger, s = current_status()
    left = max(0.0, s["allowance"] - s["spent_today"])
    if s["state"] in ("exhausted", "bankrupt"):
        pool = GREETINGS_BROKE
    elif s["bonus_label"] == "weekend bonus":
        pool = GREETINGS_WEEKEND
    elif s["bonus_label"]:
        pool = GREETINGS_OVERTIME
    else:
        pool = GREETINGS_CORE
    msg = "💼 %s %s available today" % (random.choice(pool), money(left))
    if s["bonus_label"]:
        msg += " (incl. ×%.1f %s)" % (s["multiplier"], s["bonus_label"])
    msg += " · month %s / %s" % (money(s["spent_month"]), money(s["monthly"]))
    emit({"systemMessage": msg})


def safe(fn):
    """Hooks must never break Claude Code. Errors go to stderr, exit 0."""
    try:
        fn()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("austerity: %s\n" % e)
        sys.exit(0)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_statusline():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        payload = {}
    record_official(dt.datetime.now().astimezone(), payload)
    _now, _cfg, _ledger, s = current_status(max_age_s=10)
    emoji, _ = mood(s["ratio"])
    parts = [
        "💼 %s/%s %s" % (money(s["spent_today"]), money(s["allowance"]), bar(s["ratio"], 8)),
        "month %s/%s%s" % (money(s["spent_month"]), money(s["monthly"]),
                           " ✓" if s["source"] == "official" else ""),
    ]
    if s["bonus_label"]:
        parts.append("🌙 ×%.1f %s" % (s["multiplier"], s["bonus_label"]))
    if s["override"]:
        parts.append("🚨 incident mode")
    parts.append("Controlling %s" % emoji)
    print(" · ".join(parts))


def cmd_report():
    _now, cfg, _ledger, s = current_status()
    print(format_report(s, cfg))


def spent_yesterday(now, cfg):
    """Yesterday's spend, or None if yesterday was in another month."""
    yesterday = (now - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    if yesterday[:7] != now.strftime("%Y-%m"):
        return None
    days = scan_usage(now, cfg.get("prices"), max_age_s=60)
    return days.get(yesterday, 0.0) * cfg["price_multiplier"]


def cmd_standup():
    now, cfg, _ledger, s = current_status()
    rng = random.Random(s["today"])
    spent_yesterday_usd = spent_yesterday(now, cfg)
    print("DAILY TOKEN STANDUP · %s" % s["today"])
    print("")
    if spent_yesterday_usd is None:
        print("Yesterday: belongs to a closed fiscal period. We don't talk about it.")
    else:
        print("Yesterday: %s. Invested %s." % (rng.choice(STANDUP_YESTERDAY), money(spent_yesterday_usd)))
    print("Today: deliver value within an approved envelope of %s (%d%% consumed)."
          % (money(s["allowance"]), pct(s["ratio"])))
    print(STANDUP_BLOCKERS[s["state"]])
    print("Burn rate vs. fair share: %s" % bar(s["ratio"]))


def cmd_standup_facts():
    """Plain numbers for the /austerity:standup command to write about."""
    now, cfg, _ledger, s = current_status()
    y = spent_yesterday(now, cfg)
    facts = [
        ("date", "%s (%s)" % (s["today"], now.strftime("%A"))),
        ("spent_yesterday", "previous month, closed fiscal period" if y is None else money(y)),
        ("spent_today", money(s["spent_today"])),
        ("allowance_today", money(s["allowance"])),
        ("used_today", "%d%%" % pct(s["ratio"])),
        ("spent_month", "%s of %s" % (money(s["spent_month"]), money(s["monthly"]))),
        ("days_left_in_month", s["remaining_days"]),
        ("state", {"ok": "on track", "warn": "almost out for today",
                   "exhausted": "out of budget for today",
                   "bankrupt": "monthly budget used up"}[s["state"]]),
        ("bonus", s["bonus_label"] or "none (core hours)"),
        ("emergency_overrides_this_month", s["incidents"]),
        ("controlling_mood", "%s %s" % mood(s["ratio"])),
    ]
    for key, value in facts:
        print("%s: %s" % (key, value))


def cmd_request_increase():
    now, cfg, ledger, s = current_status()
    book = month_book(ledger, now)
    book["requests"] += 1
    rng = random.Random()
    roll = rng.random()
    if book["approvals"] < 2 and roll < 0.07:
        book["approvals"] += 1
        book["approved_usd"] += 2.5
        decision = "APPROVED: +$2.50 added to this month's budget (one coffee-equivalent)"
        reason = rng.choice(APPROVALS)
    elif roll < 0.30:
        decision = "PENDING"
        reason = rng.choice(PENDING)
    else:
        decision = "DENIED"
        reason = rng.choice(REJECTIONS)
    write_json(LEDGER_PATH, ledger)
    print("Decision: %s" % decision)
    print("Reason: %s" % reason)
    print("Request number this month: %d" % book["requests"])
    print("Approvals this month: %d of %d" % (book["approvals"], book["requests"]))


def cmd_set_budget(value):
    amount = float(value)
    if amount <= 0:
        raise SystemExit("Budget must be positive. Management appreciates the gesture, though.")
    load_config()
    cfg = read_json(CONFIG_PATH, {})
    cfg["monthly_budget_usd"] = amount
    write_json(CONFIG_PATH, cfg)
    print("Monthly budget set to %s. The Budget Committee has approved this number without reading it." % money(amount))
    print("Config: %s" % CONFIG_PATH)


def cmd_install_statusline(force=False):
    ensure_home()
    with open(os.path.abspath(__file__), "rb") as f:
        code = f.read()
    with open(STATUSLINE_COPY, "wb") as f:
        f.write(code)
    command = 'python3 "%s" statusline' % STATUSLINE_COPY
    settings = read_json(SETTINGS_PATH, {})
    existing = settings.get("statusLine")
    if existing and existing.get("command") != command and not force:
        print("EXISTING_STATUSLINE: %s" % json.dumps(existing))
        print("Not changed. Re-run with --force to replace it.")
        return
    settings["statusLine"] = {"type": "command", "command": command, "padding": 0}
    write_settings(settings)
    print("Status line installed: %s" % command)


def write_settings(settings):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SETTINGS_PATH), prefix=".settings-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, SETTINGS_PATH)


def cmd_config():
    cfg = load_config()
    print("Config file: %s" % CONFIG_PATH)
    print(json.dumps(cfg, indent=2))


USAGE = """austerity %s — Management-Confirmed Token Usage Distributor

  report                   budget report
  standup                  daily standup in corporate speak
  standup-facts            the numbers behind the standup
  request-increase         file a budget increase request
  set-budget <usd>         set the monthly budget
  config                   show config path and values
  statusline               one-line status for Claude Code's status line
  install-statusline [--force]   add the status line to ~/.claude/settings.json
  hook-prompt|hook-tool|hook-session   used by the plugin hooks
""" % VERSION


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "report"
    if cmd == "hook-prompt":
        safe(hook_prompt)
    elif cmd == "hook-tool":
        safe(hook_tool)
    elif cmd == "hook-session":
        safe(hook_session)
    elif cmd == "statusline":
        safe(cmd_statusline)
    elif cmd == "report":
        cmd_report()
    elif cmd == "standup":
        cmd_standup()
    elif cmd == "standup-facts":
        cmd_standup_facts()
    elif cmd == "request-increase":
        cmd_request_increase()
    elif cmd == "set-budget" and len(argv) > 2:
        cmd_set_budget(argv[2])
    elif cmd == "install-statusline":
        cmd_install_statusline(force="--force" in argv)
    elif cmd == "config":
        cmd_config()
    else:
        print(USAGE)


if __name__ == "__main__":
    main(sys.argv)
