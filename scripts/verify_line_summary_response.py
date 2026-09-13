"""Fail closed on summary delivery results; never echo response bodies or secrets."""

from __future__ import annotations

import json
import sys


MAX_RESPONSE_CHARACTERS = 16_384
SLOTS = {"morning", "noon", "evening"}
RETRY_COUNTS = ("processed", "sent", "deferred_unconfigured", "ignored_stale", "ignored_legacy_email")


def main(argv=None, *, stdin=None, stdout=None):
    args = list(sys.argv[1:] if argv is None else argv)
    source = sys.stdin if stdin is None else stdin
    destination = sys.stdout if stdout is None else stdout
    safe = {"result": "invalid_response"}
    exit_code = 1
    if len(args) != 1 or args[0] not in SLOTS:
        safe["result"] = "invalid_expected_slot"
    else:
        try:
            raw = source.read(MAX_RESPONSE_CHARACTERS + 1)
        except (UnicodeError, OSError):
            print('{"result":"response_read_error"}', file=destination)
            return 1
        if len(raw) > MAX_RESPONSE_CHARACTERS:
            safe["result"] = "response_too_large"
        else:
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError, RecursionError):
                payload = None
                safe["result"] = "invalid_json"
            if isinstance(payload, dict):
                queued = payload.get("queued")
                deduplicated = payload.get("deduplicated")
                channels = payload.get("channels")
                valid = (
                    payload.get("slot") == args[0]
                    and type(queued) is int and queued in (0, 1)
                    and type(deduplicated) is int and deduplicated in (0, 1)
                    and queued + deduplicated == 1
                    and isinstance(channels, dict)
                    and set(channels) == {"line"}
                )
                if valid:
                    line_status = channels.get("line")
                    safe = {"result": "summary_not_accepted", "slot": args[0],
                            "queued": queued, "deduplicated": deduplicated}
                    if line_status in ("sent", "failed", "pending", "skipped"):
                        safe["line_status"] = line_status
                    if line_status == "sent":
                        safe["result"] = (
                            "new_summary_api_accepted" if queued else "summary_previously_api_accepted"
                        )
                        exit_code = 0
                    retry = payload.get("retry")
                    if isinstance(retry, dict):
                        safe["retry"] = {
                            key: retry[key] for key in RETRY_COUNTS
                            if type(retry.get(key)) is int and 0 <= retry[key] <= 100_000
                        }
    print(json.dumps(safe, ensure_ascii=True, separators=(",", ":")), file=destination)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
