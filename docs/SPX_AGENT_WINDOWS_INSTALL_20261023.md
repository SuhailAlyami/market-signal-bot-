# Windows SPX local-agent installation ? 2026-10-23

Source branch: `research/spx-only-price-watch-20261022`, fetched commit
`1be14a32b464e37a9ddc1b944f6d985b7cb36d88`. Fetch and setup used a separate
repository; the existing market-signal-bot working tree and index were not used.
The worker is a linked worktree on `research/local-spx-agent`.

Available requirements were resolved without admin/service purchases: existing
ChatGPT-authenticated Codex CLI0.162.0-alpha.17.2; official MinGit2.56.0.windows.3
verified SHA256`2e5619966e588fde5f8122c5557cad50c0fbafcaed736689f40ec1dfb1d78ea7`;
a stable per-user Python3.12 runtime with existing-version ibapi9.81.1.post1 and
pandas-market-calendars5.5.0. No auth tokens/keys were read, printed or copied.
Git uses the already authenticated gh credential helper, with the unused bundled
credential-manager helper cleared for this isolated repository only.

The installer now pins resolved Python/Git/Codex directories in a private Python
launcher outside Git. Task Scheduler does not inherit the VS Code terminal PATH;
otherwise an apparently successful registration could run without Git/Codex.
The task uses pythonw for hidden execution. No global/user PATH or authentication
settings were changed. The Codex executable is pinned to the existing installed
version; if an extension update removes it, reinstall with the new CLI location.

The registered task is `Suhail SPX Research`: current interactive user, limited
privileges, at logon and every15minutes, network required, IgnoreNew overlap,
20minute task cap. The runner retains its two-calls/UTCday and one-hour model
backoff; model timeout15minutes. No experimental alerts, deployments or trades.
This works while the PC is on, awake, networked and the user logged in; VS Code
need not remain running. This does not create independent cloud hosting.

The installer was actually executed and the task launched the first Codex call.
Registration is not evidence that the cycle completes, that SPX data is usable,
or that detection has predictive quality. The final state/remote checkpoint is
recorded after that cycle; private logs and authentication are never uploaded.
A WAIT_DATA/NOT_READY result requires new raw.json input to wake research, and the
runner does not silently collect it while waiting. See SPX_LOCAL_AGENT.md.

## Actual first cycle and host recovery

First scheduled model call started12:15:51UTC and finished with BLOCKED because
its linked Git index was outside the workspace sandbox. TCP4001 and four
synthetic collector tests succeeded; no API data was collected by that call.
The model correctly did not call that detector success. Its three reviewed
checkpoint files were committed and pushed by the host as
4bdb98ef947ec25ee7c18e4788ea9654ca37b2f4, with private log excluded.

A guarded host checkpoint step now accepts an exact manifest of at most20 files:
RESUME or NEW research scripts/tests/docs/derived reports only. It rejects
unlisted changes, tracked production files, raw/private/instruction files,
traversal, links, renames and deletions. Only explicit files are staged.
The model remains workspace-write; no sandbox/ACL weakening or credential copy.
The manifest is part of structured output. Budget/backoff/failure behavior is
unchanged. Daily collector YYYY-MM-DD.raw.json now also wakes WAIT_DATA; derived
reports do not. All final focused worker/guard tests pass.

After the pre-acquisition checkpoint was pushed, the host executed the existing
collector ONCE for Oct19: actual native SPX/IND/CBOE historical bars,390/390,
complete=True. Raw data remains private and unscored. This proves that specific
historical acquisition, not live quote mode, latency or predictive quality.
No detector outcomes or options, orders, subscriptions or alerts were requested.
The separate worker branch contains the final recovery/acquisition checkpoint.
