"""Re-download the keyless Dukascopy bid 1-minute history.

The committed files under data/archive/dukascopy/spx_history already contain
the 2025-01-02 .. 2026-11-10 RTH sample. This script only documents the
public command. It does not need an account or an API key.

Requires Node.js and network access:

    npx --yes dukascopy-node -i spyususd -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv

Instruments used for the committed sample:
    spyususd, qqqususd, usa500idxusd, volidxusd

Volume from this feed is broker/CFD volume, not exchange volume.
The Volatility Index CFD is not official CBOE VIX.
"""
from __future__ import annotations

import sys

COMMANDS = (
    "npx --yes dukascopy-node -i spyususd -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv",
    "npx --yes dukascopy-node -i qqqususd -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv",
    "npx --yes dukascopy-node -i usa500idxusd -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv",
    "npx --yes dukascopy-node -i volidxusd -from 2025-01-01 -to 2026-11-11 -t m1 -p bid -f csv",
)
LONG_HISTORY = (
    "npx --yes dukascopy-node -i usa500idxusd -from 2010-01-01 -to 2026-11-12 -t m5 -p bid -f csv",
    "npx --yes dukascopy-node -i usatechidxusd -from 2010-01-01 -to 2026-11-12 -t m5 -p bid -f csv",
    "npx --yes dukascopy-node -i spyususd -from 2010-01-01 -to 2026-11-12 -t m5 -p bid -f csv",
    "npx --yes dukascopy-node -i qqqususd -from 2010-01-01 -to 2026-11-12 -t m5 -p bid -f csv",
    "npx --yes dukascopy-node -i volidxusd -from 2010-01-01 -to 2026-11-12 -t m5 -p bid -f csv",
)


def main() -> int:
    print("Committed sample: data/archive/dukascopy/spx_history")
    print("Re-download with dukascopy-node (no key). Filter the CSV to 09:30-15:59 America/New_York.")
    for command in COMMANDS:
        print(command)
    print("Long 5-minute history. USA500 on this feed starts 2011-09-18, not 2010. Do not commit the CSV.")
    for command in LONG_HISTORY:
        print(command)
    print("Dukascopy volume is CFD volume. VIX CFD is a weak proxy, not CBOE VIX.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
