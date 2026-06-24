#!/usr/bin/env python3
"""Mark a displayed edit plan approved after explicit user acceptance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from common import ReelError, load_json, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args()

    plan = load_json(args.plan)
    if plan.get("schema_version") != 1 or not plan.get("clips"):
        raise ReelError("Not a valid edit plan.")
    plan["approved"] = True
    plan["approval"] = {
        "approved_by": args.approved_by,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json(args.plan, plan)
    print(args.plan)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReelError as error:
        raise SystemExit(str(error)) from error
