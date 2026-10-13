import logging

import pytest


@pytest.fixture(autouse=True)
def _restore_audit_logger():
    """main() installs a non-propagating audit handler; keep that out of other tests."""
    lg = logging.getLogger("oraclarr_mcp.audit")
    handlers, propagate, level = list(lg.handlers), lg.propagate, lg.level
    yield
    lg.handlers[:] = handlers
    lg.propagate, lg.level = propagate, level
