"""Re-download the keyless Dukascopy history used by trend_24h_study.py.

The files are not stored in git because the combined archives are large.
No account and no API key are required. Requires Node.js.

    npx --yes dukascopy-node -i usa500idxusd -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv

All-session index CFDs (UTC day files, not RTH-only):
    usa500idxusd   US 500, an ES-style CFD, not the official index
    usatechidxusd  Nasdaq-100 CFD, an NQ-style proxy
    volidxusd      volatility CFD, not CBOE VIX, and gappy

RTH names used as breadth and cross-asset features:
    aaplususd msftususd nvdaususd amznususd googlususd metaususd
    avgoususd tslaususd brkbususd jpmususd
    xlkususd xlfususd xleususd xlvususd xliususd xlpususd xluususd xlyususd
    iefususd tltususd ustbondusd dxyusd usdjpyusd

Volume on this feed is CFD volume. The study uses price, not that volume.
Keep the raw files outside the repository and point trend_24h_study.py at them.
"""
from __future__ import annotations

import sys

ALL_SESSION = ("usa500idxusd", "usatechidxusd", "volidxusd")
RTH = (
    "aaplususd", "msftususd", "nvdaususd", "amznususd", "googlususd", "metaususd",
    "avgoususd", "tslaususd", "brkbususd", "jpmususd",
    "xlkususd", "xlfususd", "xleususd", "xlvususd", "xliususd", "xlpususd", "xluususd", "xlyususd",
    "iefususd", "tltususd", "ustbondusd", "dxyusd", "usdjpyusd",
)


def main() -> int:
    print("Dukascopy bid 1-minute, 2025-01-01 to 2026-11-11 UTC. No key.")
    print("All sessions:")
    for symbol in ALL_SESSION:
        print(f"npx --yes dukascopy-node -i {symbol} -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv")
    print("RTH names (filter 09:30-15:59 America/New_York after download):")
    for symbol in RTH:
        print(f"npx --yes dukascopy-node -i {symbol} -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv")
    print("Do not commit the raw files. USA500/USATECH volume is CFD volume.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
