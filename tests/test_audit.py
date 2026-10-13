import logging

from oraclarr_mcp.audit import audit


def test_audit_writes_one_info_line(caplog):
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        audit("executed", tool="start_job", instance="sonarr", action="refresh",
              target=12, plan_id="abc", command_id=None)
    (rec,) = caplog.records
    assert rec.name == "oraclarr_mcp.audit" and rec.levelno == logging.INFO
    msg = rec.getMessage()
    assert msg.startswith("audit event=executed")
    assert "instance=sonarr" in msg and "target=12" in msg and "command_id" not in msg


def test_audit_values_cannot_start_a_new_line_or_forge_fields(caplog):
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        audit("x", detail="a b\nc\r\td")
    (rec,) = caplog.records
    msg = rec.getMessage()
    assert "\n" not in msg and "\r" not in msg and "\t" not in msg
    assert "detail=a_b_c__d" in msg


def test_audit_logging_installs_one_plain_stderr_line_per_event():
    import io
    import sys

    from oraclarr_mcp.audit import install_audit_logging

    lg = logging.getLogger("oraclarr_mcp.audit")
    before = (list(lg.handlers), lg.propagate, lg.level)
    try:
        install_audit_logging()
        install_audit_logging()
        owned = [h for h in lg.handlers if getattr(h, "_oraclarr_audit", False)]
        assert len(owned) == 1
        assert owned[0].stream is sys.stderr and lg.propagate is False
        buf = io.StringIO()
        owned[0].setStream(buf)
        fields = {f"field{i}": "v" * 20 for i in range(12)}
        audit("executed", tool="start_job", plan_id="p" * 16, command_id=777, **fields)
        lines = buf.getvalue().splitlines()
        assert len(lines) == 1
        assert "audit event=executed" in lines[0]
        assert "plan_id=" + "p" * 16 in lines[0] and "command_id=777" in lines[0]
        assert all(f"field{i}=" in lines[0] for i in range(12))
    finally:
        lg.handlers[:] = before[0]
        lg.propagate, lg.level = before[1], before[2]
