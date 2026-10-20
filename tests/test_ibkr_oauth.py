"""Exercise actual SDK discovery, registration, PKCE and token persistence offline."""
import json
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

import httpx

from ibkr_mcp import ENDPOINT
from ibkr_mcp_client import PrivateOAuthStorage, oauth_provider


class OAuthProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_pkce_round_trip(self):
        metadata = ENDPOINT + "/.well-known/oauth-protected-resource"
        auth = "https://api.ibkr.com"
        redirected = {}
        calls = []

        def respond(request):
            calls.append((request.method, str(request.url)))
            url = str(request.url)
            if url == ENDPOINT:
                if request.headers.get("Authorization") == "Bearer test-access":
                    return httpx.Response(200, json={"ok": True})
                return httpx.Response(401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'})
            if url == metadata:
                return httpx.Response(200, json={"resource": ENDPOINT, "authorization_servers": [auth],
                                                "scopes_supported": ["mcp.read", "mcp.write"]})
            if url == auth + "/.well-known/oauth-authorization-server":
                return httpx.Response(200, json={
                    "issuer": auth, "authorization_endpoint": auth + "/oauth2/authorize",
                    "token_endpoint": auth + "/oauth2/token", "registration_endpoint": auth + "/oauth2/register",
                    "response_types_supported": ["code"], "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": ["mcp.read"]})
            if url == auth + "/oauth2/register":
                body = json.loads(request.content)
                self.assertEqual(body["scope"], "mcp.read")
                self.assertEqual(body["token_endpoint_auth_method"], "none")
                return httpx.Response(201, json={**body, "client_id": "test-client"})
            if url == auth + "/oauth2/token":
                body = parse_qs(request.content.decode())
                self.assertEqual(body["grant_type"], ["authorization_code"])
                self.assertTrue(body["code_verifier"][0])
                self.assertEqual(body["resource"], [ENDPOINT])
                return httpx.Response(200, json={"access_token": "test-access", "token_type": "Bearer",
                                                "expires_in": 3600, "scope": "mcp.read"})
            raise AssertionError("Unexpected OAuth request: " + url)

        async def redirect(url):
            redirected.update(parse_qs(urlparse(url).query))
            self.assertEqual(redirected["scope"], ["mcp.read"])
            self.assertEqual(redirected["code_challenge_method"], ["S256"])

        async def receive():
            return "test-code", redirected["state"][0]

        with tempfile.TemporaryDirectory() as directory:
            storage = PrivateOAuthStorage(directory)
            oauth = oauth_provider(storage, redirect, receive)
            async with httpx.AsyncClient(auth=oauth, transport=httpx.MockTransport(respond)) as client:
                response = await client.get(ENDPOINT)
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await storage.get_tokens()).access_token, "test-access")
            self.assertEqual((await storage.get_client_info()).client_id, "test-client")
        self.assertIn(("POST", auth + "/oauth2/register"), calls)
