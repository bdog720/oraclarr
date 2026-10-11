import time
from oraclarr_mcp.budget import set_deadline, reset_deadline, remaining


def test_remaining_is_none_without_deadline():
    assert remaining() is None


def test_remaining_counts_down_and_resets():
    token = set_deadline(5)
    try:
        left = remaining()
        assert left is not None and 4.5 < left <= 5
        time.sleep(0.05)
        assert remaining() < left
    finally:
        reset_deadline(token)
    assert remaining() is None
