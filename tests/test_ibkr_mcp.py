import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from ibkr_mcp import collect_spx, inspect_snapshot, report_health, save_report, unwrap, READ_TOOLS
from ibkr_mcp_client import PrivateOAuthStorage, ReadOnlyTools, run_collection

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


def snapshot(state="REALTIME", book_time=True):
    book = {"bid": 26.2, "ask": 26.4}
    if book_time:
        book["ts"] = NOW.timestamp()
    return {"last": {"price": 7691.92, "ts": NOW.timestamp()},
            "top-status": {"status": state}, "bid-ask": book}


class SnapshotTests(unittest.TestCase):
    def test_real_connector_text_envelope_and_hyphen_keys(self):
        raw = {"structuredContent": None, "content": [{"type": "text", "text": json.dumps(snapshot())}]}
        self.assertTrue(inspect_snapshot(raw, NOW)["quote_live_verified"])

    def test_realtime_last_trade_does_not_certify_bid_ask_time(self):
        result = inspect_snapshot(snapshot(book_time=False), NOW)
        self.assertTrue(result["last_live_verified"])
        self.assertFalse(result["quote_live_verified"])
        self.assertEqual(result["quote_reason"], "missing_bid_ask_timestamp")
        self.assertEqual(result["bid"], 26.2)

    def test_frozen_delayed_and_unknown_are_not_live(self):
        for state in ("FROZEN", "DELAYED", "UNAVAILABLE", "unknown"):
            with self.subTest(state=state):
                report = inspect_snapshot(snapshot(state), NOW)
                self.assertFalse(report["quote_live_verified"])
                self.assertFalse(report["last_live_verified"])

    def test_old_future_and_missing_quote_times_rejected(self):
        for ts in (NOW.timestamp() - 11, NOW.timestamp() + 1, None, float("nan"), True):
            raw = snapshot()
            raw["bid-ask"]["ts"] = ts
            self.assertFalse(inspect_snapshot(raw, NOW)["quote_live_verified"])

    def test_zero_crossed_and_nonfinite_books_rejected(self):
        for bid, ask in ((0, 1), (2, 1), (float("nan"), 1), (1, float("inf"))):
            raw = snapshot()
            raw["bid-ask"].update(bid=bid, ask=ask)
            self.assertFalse(inspect_snapshot(raw, NOW)["quote_live_verified"])

    def test_invalid_clocks_and_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            inspect_snapshot(snapshot(), NOW.replace(tzinfo=None))
        for limit in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                inspect_snapshot(snapshot(), NOW, limit)

    def test_tool_errors_and_ambiguous_blocks_rejected(self):
        for raw in ({"isError": True}, {"content": []}, {"content": [{"type": "text", "text": "[]"}]}):
            with self.assertRaises(ValueError):
                unwrap(raw)


class FakeMarket:
    def __init__(self, *, frozen=False, book_time=True, fail=False):
        self.calls = []
        self.frozen, self.book_time, self.fail = frozen, book_time, fail

    async def __call__(self, name, args):
        self.calls.append((name, args))
        if self.fail:
            raise RuntimeError("Authorization: Bearer secret-must-never-escape")
        if name == "search_contracts":
            return {"results": [
                {"symbol": "SPXL", "exchange": "ARCA", "country_code": "US", "underlying_contract_id": 8,
                 "sections": [{"security_type": "OPT"}]},
                {"symbol": "SPX", "exchange": "CBOE", "country_code": "US", "underlying_contract_id": 1,
                 "sections": [{"security_type": "IND"}, {"security_type": "OPT"}]}]}
        if name == "get_price_snapshot":
            return snapshot("FROZEN" if args["contract_id"] == 1 and self.frozen else "REALTIME", self.book_time)
        if name == "get_option_parameters":
            return {"expirations": [
                {"date": "20261020", "trading_class": "SPX", "id": "wrong_monthly"},
                {"date": "20261020", "trading_class": "SPXW", "id": "opaque-provider-expiry"}]}
        if name == "get_option_data":
            return {"exchange": "SMART", "currency": "USD", "contracts": [
                {"strike": "7690", "call_contract_id": 2, "put_contract_id": 3,
                 "call_description": "SPXW 20 Oct 2026 7690 Call",
                 "put_description": "SPXW 20 Oct 2026 7690 Put"}]}
        raise AssertionError(name)


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_validated_quotes_reach_existing_selector_as_research_only(self):
        feed = FakeMarket()
        report = await collect_spx(feed, now=NOW)
        self.assertEqual(report["readiness"], "RESEARCH_ONLY")
        self.assertEqual(set(report["candidates"]), {"CALL", "PUT"})
        self.assertFalse(report["orders_enabled"])
        self.assertTrue(all(name in READ_TOOLS for name, _ in feed.calls))
        chain_args = next(args for name, args in feed.calls if name == "get_option_data")
        self.assertEqual(chain_args["expiration_id"], "opaque-provider-expiry")
        self.assertLess(chain_args["min_strike"], 7691.92 - 25)
        self.assertGreater(chain_args["max_strike"], 7691.92 + 25)

    async def test_real_observed_shape_remains_not_ready_without_quote_timestamp(self):
        report = await collect_spx(FakeMarket(frozen=True, book_time=False), now=NOW)
        self.assertEqual(report["status"], "collected")
        self.assertEqual(report["readiness"], "NOT_READY")
        self.assertEqual(report["candidates"], {})
        self.assertEqual(report["underlying"]["feed_status"], "FROZEN")
        self.assertEqual(len(report["contracts"]), 2)
        self.assertTrue(all(x["bid"] == 26.2 for x in report["contracts"]))

    async def test_fresh_last_without_quote_time_cannot_create_candidate(self):
        report = await collect_spx(FakeMarket(book_time=False), now=NOW)
        self.assertEqual(report["reason"], "no_timestamp_verified_option_quotes")

    async def test_provider_error_is_redacted(self):
        report = await collect_spx(FakeMarket(fail=True), now=NOW)
        self.assertEqual(report["status"], "error")
        self.assertNotIn("secret-must-never-escape", json.dumps(report))

    async def test_slow_collection_rechecks_index_age(self):
        times = iter([NOW] * 5 + [NOW + timedelta(seconds=30)] * 20)
        report = await collect_spx(FakeMarket(), clock=lambda: next(times))
        self.assertEqual(report["readiness"], "NOT_READY")
        self.assertFalse(report["underlying"]["last_live_verified"])

    async def test_missing_expiry_fails_without_inventing_an_id(self):
        feed = FakeMarket()
        async def call(name, args):
            if name == "get_option_parameters":
                return {"expirations": []}
            return await feed(name, args)
        report = await collect_spx(call, now=NOW)
        self.assertEqual(report["reason"], "no_unique_today_spxw_expiry")
        self.assertFalse(any(name == "get_option_data" for name, _ in feed.calls))


class StorageAndTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_authorization_does_not_attempt_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("httpx.AsyncClient") as client:
                result = await run_collection(storage=PrivateOAuthStorage(directory))
                client.assert_not_called()
            self.assertEqual(result["status"], "authorization_required")

    async def test_scope_and_credentials_not_in_repo(self):
        with self.assertRaises(ValueError):
            PrivateOAuthStorage(Path(__file__).resolve().parents[1] / "auth")
        with tempfile.TemporaryDirectory() as directory:
            from mcp.shared.auth import OAuthToken
            store = PrivateOAuthStorage(directory)
            await store.set_tokens(OAuthToken(access_token="not-a-real-token", token_type="Bearer"))
            if os.name != 'nt':
                self.assertEqual((Path(directory) / "tokens.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((await store.get_tokens()).access_token, "not-a-real-token")

    async def test_broadened_oauth_file_access_is_rejected(self):
        from mcp.shared.auth import OAuthToken
        with tempfile.TemporaryDirectory() as directory:
            store = PrivateOAuthStorage(directory)
            await store.set_tokens(OAuthToken(access_token='test-only', token_type='Bearer'))
            path = Path(directory) / 'tokens.json'
            if os.name == 'nt':
                import ntsecuritycon
                import win32security
                descriptor = win32security.GetNamedSecurityInfo(
                    str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION)
                acl = descriptor.GetSecurityDescriptorDacl()
                acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_GENERIC_READ,
                                       win32security.CreateWellKnownSid(win32security.WinWorldSid))
                win32security.SetNamedSecurityInfo(
                    str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION,
                    None, None, acl, None)
            else:
                os.chmod(path, 0o644)
            with self.assertRaises(ValueError):
                await store.get_tokens()

    async def test_acl_failure_cannot_persist_oauth_data(self):
        from mcp.shared.auth import OAuthToken
        with tempfile.TemporaryDirectory() as directory:
            store = PrivateOAuthStorage(directory)
            with patch('ibkr_mcp_client._protect_oauth_path', side_effect=[None, PermissionError('denied')]):
                with self.assertRaises(PermissionError):
                    await store.set_tokens(OAuthToken(access_token='test-only', token_type='Bearer'))
            self.assertEqual(list(Path(directory).iterdir()), [])

    async def test_account_and_order_tools_blocked_before_transport(self):
        session = SimpleNamespace(call_tool=AsyncMock())
        descriptions = [SimpleNamespace(name="ibkr___" + name, inputSchema={"type": "object"}) for name in READ_TOOLS]
        client = ReadOnlyTools(session, descriptions)
        for name in ("submit_order", "create_order_instruction", "get_account_positions", "get_account_balances"):
            with self.assertRaises(PermissionError):
                await client(name, {})
        session.call_tool.assert_not_called()

    async def test_broader_oauth_tokens_never_persist(self):
        from mcp.shared.auth import OAuthToken
        with tempfile.TemporaryDirectory() as directory:
            store = PrivateOAuthStorage(directory)
            with self.assertRaises(ValueError):
                await store.set_tokens(OAuthToken(access_token="test", token_type="Bearer", scope="mcp.read mcp.write"))
            self.assertFalse((Path(directory) / "tokens.json").exists())

    async def test_exact_tool_name_and_input_schema(self):
        session = SimpleNamespace(call_tool=AsyncMock(return_value={"results": []}))
        descriptions = [SimpleNamespace(name=name, inputSchema={"type": "object", "required": ["query"]})
                        for name in READ_TOOLS]
        client = ReadOnlyTools(session, descriptions)
        with self.assertRaises(Exception):
            await client("search_contracts", {})
        session.call_tool.assert_not_called()
        await client("search_contracts", {"query": "SPX"})
        session.call_tool.assert_awaited_once_with("search_contracts", arguments={"query": "SPX"})


class HealthTests(unittest.TestCase):
    def test_health_contains_no_quotes_or_secret_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = {"status": "collected", "readiness": "RESEARCH_ONLY", "observed_at": NOW.isoformat(),
                      "underlying": {"feed_status": "REALTIME", "last": 7691.92}, "contracts": []}
            save_report(report, path)
            self.assertNotIn("7691.92", json.dumps(report_health(path, NOW)))
            self.assertEqual(report_health(path, NOW + timedelta(minutes=4))["status"], "stale_report")
            self.assertEqual(report_health(path, NOW - timedelta(seconds=1))["readiness"], "NOT_READY")

    def test_missing_or_corrupt_report_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            self.assertEqual(report_health(path, NOW)["status"], "unavailable")
            path.write_text("broken")
            self.assertEqual(report_health(path, NOW)["status"], "unavailable")
