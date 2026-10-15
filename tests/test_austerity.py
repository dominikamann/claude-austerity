import datetime as dt
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

TMP = tempfile.mkdtemp()
os.environ["CLAUDE_CONFIG_DIR"] = TMP
os.environ["AUSTERITY_HOME"] = os.path.join(TMP, "austerity")
os.environ.pop("AUSTERITY_MONTHLY_BUDGET", None)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("austerity", os.path.join(ROOT, "scripts", "austerity.py"))
austerity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(austerity)

TZ = dt.timezone.utc
CFG = dict(austerity.DEFAULT_CONFIG)


def at(day, hour):
    # October 2026: the 15th is a Thursday, the 17th a Saturday.
    return dt.datetime(2026, 10, day, hour, 0, tzinfo=TZ)


def empty_ledger():
    return {"months": {}, "override_until": None}


def line(msg_id, ts, model="claude-opus-5-5", out=1000, req="r1"):
    return json.dumps({
        "type": "assistant",
        "timestamp": ts,
        "requestId": req,
        "message": {"id": msg_id, "model": model, "usage": {"input_tokens": 0, "output_tokens": out}},
    })


class CostTest(unittest.TestCase):
    def test_output_tokens(self):
        self.assertAlmostEqual(austerity.cost_of("claude-opus-5-5", {"output_tokens": 1_000_000}), 20.0)

    def test_cache_split_and_read(self):
        usage = {
            "input_tokens": 0,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 2_000_000,
            "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000},
        }
        # read 0.20 + 5m 4*1.25 + 1h 4*2
        self.assertAlmostEqual(austerity.cost_of("claude-opus-5-5", usage), 0.20 + 5.0 + 8.0)

    def test_fast_mode_doubles(self):
        usage = {"output_tokens": 1_000_000, "speed": "fast"}
        self.assertAlmostEqual(austerity.cost_of("claude-opus-5-5", usage), 40.0)

    def test_longest_prefix_wins(self):
        self.assertEqual(austerity.price_for("claude-opus-5-5"), (4.0, 20.0, 0.20))
        self.assertEqual(austerity.price_for("claude-opus-5"), (5.0, 25.0, 0.50))
        self.assertEqual(austerity.price_for("claude-haiku-4-5-20251001")[0], 1.0)


class BudgetTest(unittest.TestCase):
    def test_fair_share_spreads_remaining_budget(self):
        # $20 budget, nothing spent, 17 days left including the 15th.
        s = austerity.budget_status(at(15, 10), CFG, {}, empty_ledger())
        self.assertAlmostEqual(s["fair_share"], 20.0 / 17)
        self.assertEqual(s["state"], "ok")
        self.assertIsNone(s["bonus_label"])

    def test_overtime_and_weekend_bonus(self):
        s = austerity.budget_status(at(15, 20), CFG, {}, empty_ledger())
        self.assertEqual(s["bonus_label"], "overtime bonus")
        self.assertAlmostEqual(s["allowance"], 20.0 / 17 * 1.5)
        s = austerity.budget_status(at(17, 10), CFG, {}, empty_ledger())
        self.assertEqual(s["bonus_label"], "weekend bonus")
        self.assertAlmostEqual(s["allowance"], 20.0 / 15 * 2.0)

    def test_states(self):
        share = 20.0 / 17
        s = austerity.budget_status(at(15, 10), CFG, {"2026-10-15": share * 0.85}, empty_ledger())
        self.assertEqual(s["state"], "warn")
        s = austerity.budget_status(at(15, 10), CFG, {"2026-10-15": share}, empty_ledger())
        self.assertEqual(s["state"], "exhausted")
        self.assertEqual(s["next_bonus_hour"], 17)
        s = austerity.budget_status(at(15, 10), CFG, {"2026-10-02": 25.0}, empty_ledger())
        self.assertEqual(s["state"], "bankrupt")

    def test_saving_rolls_over(self):
        frugal = austerity.budget_status(at(15, 10), CFG, {"2026-10-01": 1.0}, empty_ledger())
        lavish = austerity.budget_status(at(15, 10), CFG, {"2026-10-01": 10.0}, empty_ledger())
        self.assertGreater(frugal["allowance"], lavish["allowance"])

    def test_approved_increase_counts(self):
        ledger = {"months": {"2026-10": {"approved_usd": 2.5, "requests": 1, "approvals": 1, "incidents": 0}}}
        s = austerity.budget_status(at(15, 10), CFG, {}, ledger)
        self.assertAlmostEqual(s["monthly"], 22.5)

    def test_allowance_never_exceeds_month_left(self):
        s = austerity.budget_status(at(31, 22), CFG, {"2026-10-01": 19.0}, empty_ledger())
        self.assertAlmostEqual(s["allowance"], 1.0)


class OfficialTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(austerity.OFFICIAL_PATH):
            os.remove(austerity.OFFICIAL_PATH)

    def test_official_numbers_replace_config_and_estimate(self):
        official = {"month": "2026-10", "used_usd": 30.0, "limit_usd": 50.0, "at": 0}
        s = austerity.budget_status(at(15, 10), CFG, {"2026-10-15": 1.0, "2026-10-01": 99.0}, empty_ledger(), official)
        self.assertEqual(s["source"], "official")
        self.assertAlmostEqual(s["monthly"], 50.0)
        self.assertAlmostEqual(s["spent_month"], 30.0)
        # 50 - (30 - 1 today) = 21 left for 17 days
        self.assertAlmostEqual(s["fair_share"], 21.0 / 17)

    def test_statusline_payload_is_recorded_and_loaded(self):
        now = at(15, 10)
        payload = {"rate_limits": {"spend_limit": {"used_usd": 12.5, "limit_usd": 20, "used_percentage": 62.5}}}
        austerity.record_official(now, payload)
        data = austerity.load_official(now, CFG)
        self.assertEqual((data["used_usd"], data["limit_usd"]), (12.5, 20.0))
        self.assertIsNone(austerity.load_official(at(15, 10).replace(month=11), CFG))
        self.assertIsNone(austerity.load_official(now, dict(CFG, budget_source="config")))

    def test_payload_without_spend_limit_is_ignored(self):
        austerity.record_official(at(15, 10), {"rate_limits": {"five_hour": {"used_percentage": 3}}})
        self.assertFalse(os.path.exists(austerity.OFFICIAL_PATH))


class ScanTest(unittest.TestCase):
    def setUp(self):
        for p in (austerity.CACHE_PATH,):
            if os.path.exists(p):
                os.remove(p)
        self.dir = os.path.join(austerity.PROJECTS_DIR, "proj")
        os.makedirs(self.dir, exist_ok=True)
        for name in os.listdir(self.dir):
            os.remove(os.path.join(self.dir, name))

    def write(self, name, lines, mode="w"):
        with open(os.path.join(self.dir, name), mode) as f:
            f.write("\n".join(lines) + "\n")

    def test_dedup_incremental_and_month_filter(self):
        now = at(15, 12)
        self.write("a.jsonl", [
            line("m1", "2026-10-15T08:00:00.000Z"),
            line("m1", "2026-10-15T08:00:00.000Z"),  # same message, second content block
            line("old", "2026-09-30T08:00:00.000Z"),
            "not json",
        ])
        days = austerity.scan_usage(now)
        self.assertAlmostEqual(sum(days.values()), 0.02)

        # Appended line is picked up incrementally.
        self.write("a.jsonl", [line("m2", "2026-10-15T09:00:00.000Z")], mode="a")
        days = austerity.scan_usage(now)
        self.assertAlmostEqual(sum(days.values()), 0.04)

        # A resumed session copies history into a new file: no double counting.
        self.write("b.jsonl", [line("m1", "2026-10-15T08:00:00.000Z"), line("m3", "2026-10-15T10:00:00.000Z")])
        days = austerity.scan_usage(now)
        self.assertAlmostEqual(sum(days.values()), 0.06)

    def test_partial_last_line_is_retried(self):
        now = at(15, 12)
        full = line("p1", "2026-10-15T08:00:00.000Z")
        with open(os.path.join(self.dir, "c.jsonl"), "w") as f:
            f.write(full[:40])
        self.assertAlmostEqual(sum(austerity.scan_usage(now).values()), 0.0)
        with open(os.path.join(self.dir, "c.jsonl"), "a") as f:
            f.write(full[40:] + "\n")
        self.assertAlmostEqual(sum(austerity.scan_usage(now).values()), 0.02)


class HookTest(unittest.TestCase):
    def run_hook(self, fn, payload, status):
        out = io.StringIO()
        with mock.patch.object(austerity, "current_status", return_value=status), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                mock.patch.object(sys, "stdout", out):
            fn()
        return json.loads(out.getvalue()) if out.getvalue() else None

    def status(self, spent_today):
        now = at(15, 10)
        ledger = empty_ledger()
        return now, CFG, ledger, austerity.budget_status(now, CFG, {"2026-10-15": spent_today}, ledger)

    def test_prompt_blocked_when_exhausted(self):
        res = self.run_hook(austerity.hook_prompt, {"prompt": "refactor everything"}, self.status(5.0))
        self.assertEqual(res["decision"], "block")

    def test_own_commands_pass(self):
        res = self.run_hook(austerity.hook_prompt, {"prompt": "/austerity:budget"}, self.status(5.0))
        self.assertIsNone(res)

    def test_warning_adds_context(self):
        res = self.run_hook(austerity.hook_prompt, {"prompt": "hi"}, self.status(20.0 / 17 * 0.9))
        self.assertIn("additionalContext", res["hookSpecificOutput"])

    def test_emergency_override(self):
        res = self.run_hook(austerity.hook_prompt, {"prompt": "prod is down, help"}, self.status(5.0))
        self.assertIn("Emergency override", res["systemMessage"])
        with open(austerity.SHAME_LOG) as f:
            self.assertIn("Emergency override", f.read())

    def test_tool_denied_when_exhausted(self):
        with mock.patch.object(austerity, "current_status", return_value=self.status(5.0)), \
                mock.patch.object(sys, "stdin", io.StringIO("{}")), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                austerity.hook_tool()
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
