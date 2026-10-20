"""Official MCP SDK transport for IBKR; only allowlisted market-data tools allowed.

The ChatGPT connection cannot be exported to this process. Authorize this
client separately with --authorize; subsequent runs reuse/refresh its private
OAuth state. Never ask the owner to paste session tokens into chat or GitHub.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
from urllib.parse import parse_qs, urlparse

from ibkr_mcp import ENDPOINT, READ_TOOLS, SOURCE, collect_spx

CALLBACK = "http://127.0.0.1:8765/callback"


class AuthorizationRequired(Exception):
    pass


class PrivateOAuthStorage:
    """Persist only on an operator-controlled filesystem outside the checkout."""
    def __init__(self, directory=None):
        self.directory = Path(directory or os.getenv(
            "IBKR_MCP_AUTH_DIR", str(Path.home() / ".local/share/suhail-hunter/ibkr"))).expanduser().resolve()
        root = Path(__file__).resolve().parent
        if self.directory == root or root in self.directory.parents:
            raise ValueError("OAuth storage must be outside the repository")

    def _read(self, name):
        path = self.directory / name
        if not path.exists():
            return None
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError("OAuth file permissions must be 0600")
        return json.loads(path.read_text())

    def _write(self, name, value):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".oauth-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value.model_dump(mode="json"), stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken
        value = self._read("tokens.json")
        tokens = OAuthToken.model_validate(value) if value is not None else None
        if tokens and tokens.scope and set(tokens.scope.split()) - {"mcp.read"}:
            raise ValueError("Broader OAuth scope denied")
        return tokens

    async def set_tokens(self, tokens):
        if tokens.scope and set(tokens.scope.split()) - {"mcp.read"}:
            raise ValueError("Broader OAuth scope denied")
        self._write("tokens.json", tokens)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull
        value = self._read("client.json")
        return OAuthClientInformationFull.model_validate(value) if value is not None else None

    async def set_client_info(self, client_info):
        self._write("client.json", client_info)


class LoopbackCallback:
    """Local callback only; query strings and authorization codes are never logged."""
    def __init__(self):
        self.result = None
        self.event = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != "/callback" or self.headers.get("Host") != "127.0.0.1:8765":
                    self.send_error(404)
                    return
                values = parse_qs(parsed.query)
                if len(values.get("code", [])) != 1 or len(values.get("state", [])) != 1:
                    self.send_error(400)
                    return
                owner.result = (values["code"][0], values["state"][0])
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b"Authorization received. Return to Suhail Hunter.")
                owner.event.set()

        self.server = HTTPServer(("127.0.0.1", 8765), Handler)

    async def wait(self):
        if not await asyncio.to_thread(self.event.wait, 180):
            raise AuthorizationRequired("Authorization timed out")
        return self.result

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class ReadOnlyTools:
    """Discover exact server names, validate schemas, reject every other tool."""
    def __init__(self, session, descriptions):
        self.session = session
        self.tools = {}
        for short in READ_TOOLS:
            matches = [tool for tool in descriptions if tool.name == short
                       or tool.name.endswith("_" + short)]
            if len(matches) != 1:
                raise ValueError("Missing or ambiguous read-only tool: " + short)
            self.tools[short] = matches[0]

    async def __call__(self, name, arguments):
        if name not in READ_TOOLS:
            raise PermissionError("Only read-only market-data tools are allowed")
        from jsonschema import validate
        tool = self.tools[name]
        validate(arguments, tool.inputSchema)
        return await self.session.call_tool(tool.name, arguments=arguments)


def oauth_provider(storage, redirect, receive):
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata
    from pydantic import AnyUrl, ConfigDict, field_validator

    class ReadOnlyMetadata(OAuthClientMetadata):
        # SDK scope discovery otherwise replaces the requested scope with ALL
        # scopes advertised by a resource, including trading scopes. Constrain
        # assignment as well as construction; never authorize those scopes.
        model_config = ConfigDict(validate_assignment=True)

        @field_validator("scope", mode="before")
        @classmethod
        def keep_read_only(cls, value):
            return "mcp.read"

    return OAuthClientProvider(
        server_url=ENDPOINT,
        client_metadata=ReadOnlyMetadata(
            client_name="Suhail Hunter market-data reader", redirect_uris=[AnyUrl(CALLBACK)],
            grant_types=["authorization_code", "refresh_token"], response_types=["code"],
            token_endpoint_auth_method="none", scope="mcp.read"),
        storage=storage, redirect_handler=redirect, callback_handler=receive)


async def run_collection(*, authorize=False, storage=None, history_sink=None, collector=None):
    """No implicit sign-in in a scheduled job; auth failures are observable."""
    base = {"schema_version": 1, "source": SOURCE, "orders_enabled": False,
            "readiness": "NOT_READY", "contracts": [], "candidates": {},
            "observed_at": datetime.now(timezone.utc).isoformat()}
    callback = None
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        import httpx

        storage = storage or PrivateOAuthStorage()
        if not authorize and (await storage.get_tokens() is None or await storage.get_client_info() is None):
            return {**base, "status": "authorization_required", "reason": "authorize_runtime_separately"}
        if authorize:
            callback = LoopbackCallback()
            callback.start()

        async def redirect(url):
            if not authorize:
                raise AuthorizationRequired()
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != "api.ibkr.com":
                raise ValueError("Unexpected authorization host")
            print("Open this IBKR authorization link on this machine (do not paste credentials into chat):")
            print(url)

        async def receive():
            if callback is None:
                raise AuthorizationRequired()
            return await callback.wait()

        oauth = oauth_provider(storage, redirect, receive)
        async with httpx.AsyncClient(auth=oauth, timeout=30, follow_redirects=False) as http:
            async with streamable_http_client(ENDPOINT, http_client=http) as transport:
                async with ClientSession(transport[0], transport[1]) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    tools = ReadOnlyTools(session, listing.tools)
                    return await collector(tools) if collector else await collect_spx(tools, history_sink=history_sink)
    except ImportError:
        return {**base, "status": "setup_required", "reason": "install_requirements_ibkr"}
    except AuthorizationRequired:
        return {**base, "status": "authorization_required", "reason": "renew_runtime_authorization"}
    except Exception as exc:
        from ibkr_market_data import IBKRDataUnavailable
        if isinstance(exc, IBKRDataUnavailable):
            return {**base, "status": "data_unavailable", "reason": exc.reason,
                    "error_type": type(exc).__name__}
        return {**base, "status": "error", "reason": "mcp_connection_failed",
                "error_type": type(exc).__name__}
    finally:
        if callback is not None:
            callback.close()
