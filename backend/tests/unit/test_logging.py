import json
import logging

from opspilot.logging import JsonFormatter


def test_json_formatter_outputs_json() -> None:
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    out = json.loads(JsonFormatter().format(rec))
    assert out["message"] == "hello x"
    assert out["level"] == "INFO"
