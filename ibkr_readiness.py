"""Read-only IBKR connectivity probe. Never requests orders, account balances or credentials.

Probe runs only against an operator-controlled LOCAL gateway. No connection to
Interactive Brokers is created from Render until the owner separately configures
and authenticates a proper local TWS or IB Gateway session.
"""
from __future__ import annotations
import os
import socket
from dataclasses import dataclass

@dataclass(frozen=True)
class FeedStatus:
    configured: bool
    connected_socket: bool
    reason: str

def gateway_config() -> tuple[str, int] | None:
    """Only loopback connections are permitted by design."""
    if os.getenv("IBKR_DATA_ENABLED", "false").lower() != "true":
        return None
    host = os.getenv("IBKR_GATEWAY_HOST", "127.0.0.1").strip()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("IBKR data adapter permits only local authenticated gateway")
    port = int(os.getenv("IBKR_GATEWAY_PORT", "4002"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid gateway port")
    return host, port

def inspect_socket() -> FeedStatus:
    try:
        config = gateway_config()
        if config is None:
            return FeedStatus(False, False, "IBKR disabled; Yahoo research feed remains in use")
        with socket.create_connection(config, timeout=2):
            return FeedStatus(True, True, "Gateway socket open; authentication and market data NOT verified")
    except (OSError, ValueError) as exc:
        return FeedStatus(True, False, f"IBKR not ready ({type(exc).__name__})")

def contract_plan() -> dict:
    """Planning metadata, not evidence of subscription entitlements."""
    return {
        "ES": {"secType": "FUT", "exchange": "CME", "currency": "USD", "expiry": "REQUIRED"},
        "NQ": {"secType": "FUT", "exchange": "CME", "currency": "USD", "expiry": "REQUIRED"},
        "SPX": {"secType": "IND", "exchange": "CBOE", "currency": "USD"},
        "SPX_OPTIONS": {"secType": "OPT", "exchange": "SMART", "currency": "USD",
                        "expiry": "REQUIRED", "strike": "REQUIRED", "right": "C_OR_P"},
    }
