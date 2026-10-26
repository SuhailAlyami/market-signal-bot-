# Windows SQLite resource fix

Observed regression run40263596475 at880ce329:379tests, oneerror in test_api: WinError32 deleting temporary SQLite DB. sqlite3.Connection context manager commits/rolls back transactions but does not close the connection. API requests leaked DB handles until garbage collection.

Use contextlib.closing for both API handlers and CLI watcher iteration. Transaction boundaries inside ingest/issue are preserved. No retry/sleep/deletion-error suppression or detector changes. Two regression tests assert connections are closed after normal/early returns and exceptions. Ten daily/structure/connection tests pass locally. Actual Windows CI must confirm before claiming resolution. No predictive performance improvement or local deployment implied.
