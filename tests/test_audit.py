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
