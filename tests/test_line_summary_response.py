"""Only provider acceptance may make the existing notification job green."""

import io
import json
from pathlib import Path

import pytest

from scripts.verify_line_summary_response import main


def result_payload(status="sent", **changes):
    return {"slot": "noon", "queued": 1, "deduplicated": 0,
            "channels": {"line": status}, **changes}


def run_check(payload, slot="noon", raw=False):
    output = io.StringIO()
    status = main([slot], stdin=io.StringIO(payload if raw else json.dumps(payload)), stdout=output)
    return status, output.getvalue()


def test_new_summary_api_accepted_passes_without_claiming_phone_delivery():
    status, output = run_check(result_payload())
    assert status == 0
    assert json.loads(output)["result"] == "new_summary_api_accepted"
    assert "phone" not in output


def test_existing_summary_is_not_reported_as_new_send():
    status, output = run_check(result_payload(queued=0, deduplicated=1))
    assert status == 0
    assert json.loads(output)["result"] == "summary_previously_api_accepted"


@pytest.mark.parametrize("state", ["failed", "pending", "skipped", "unknown"])
def test_nonaccepted_summary_fails_even_when_http_would_be_200(state):
    status, output = run_check(result_payload(state))
    assert status == 1
    assert "api_accepted" not in output


@pytest.mark.parametrize("payload", [
    {}, [], None, {"slot": "noon", "channels": {"line": "sent"}},
    result_payload(slot="morning"), result_payload(channels="sent"),
    result_payload(queued=True), result_payload(queued="1"),
    result_payload(queued=2), result_payload(queued=-1),
    result_payload(queued=0), result_payload(deduplicated=1),
])
def test_invalid_or_incoherent_result_never_passes(payload):
    status, _ = run_check(payload)
    assert status == 1


@pytest.mark.parametrize("body", ["", "<html>internal secret marker</html>", "{" * 18000])
def test_invalid_or_oversized_body_is_not_echoed(body):
    status, output = run_check(body, raw=True)
    assert status == 1
    assert "internal secret marker" not in output
    assert len(output) < 300


def test_unknown_private_fields_are_never_echoed():
    payload = result_payload(private_content="DO_NOT_ECHO", recipient="DO_NOT_ECHO",
                             retry={"processed": 2, "sent": 1, "ignored_stale": 3,
                                    "ignored_legacy_email": 0, "detail": "DO_NOT_ECHO"})
    status, output = run_check(payload)
    assert status == 0
    assert "DO_NOT_ECHO" not in output
    assert json.loads(output)["retry"] == {"processed": 2, "sent": 1,
                                           "ignored_stale": 3, "ignored_legacy_email": 0}


def test_invalid_expected_slot_never_passes_or_echoes_argument():
    status, output = run_check(result_payload(), slot="DO_NOT_ECHO")
    assert status == 1
    assert "DO_NOT_ECHO" not in output


def test_invalid_response_encoding_is_not_echoed():
    class InvalidEncoding:
        def read(self, _limit):
            raise UnicodeDecodeError("utf8", b"DO_NOT_ECHO\xff", 11, 12, "invalid")

    output = io.StringIO()
    assert main(["noon"], stdin=InvalidEncoding(), stdout=output) == 1
    assert "DO_NOT_ECHO" not in output.getvalue()


def test_deeply_nested_response_fails_without_traceback():
    status, output = run_check("[" * 1500 + "]" * 1500, raw=True)
    assert status == 1
    assert len(output) < 300


def test_workflow_checks_result_without_dumping_response_or_following_redirects():
    source = (Path(__file__).resolve().parents[1] / ".github/workflows/daily-admin-summary.yml").read_text(encoding="utf-8")
    assert "python3 scripts/verify_line_summary_response.py" in source
    assert "set -euo pipefail" in source
    assert "--fail-with-body" not in source
    assert "--location" not in source
    assert source.count("- cron:") == 3
