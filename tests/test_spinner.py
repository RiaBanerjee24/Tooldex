"""Unit tests for tooldex/_spinner.py."""
from unittest.mock import patch

from tooldex._spinner import Spinner


class TestSpinner:
    def test_stop_without_start_does_not_join_or_raise(self):
        Spinner().stop()  # _started is False -> must not call thread.join()

    def test_start_then_stop_joins_cleanly(self):
        with patch("builtins.open", side_effect=OSError("no tty")):
            s = Spinner()
            s.start()
            s.stop()
        assert not s._thread.is_alive()

    def test_tick_returns_immediately_when_no_tty(self):
        with patch("builtins.open", side_effect=OSError("no tty")):
            s = Spinner()
            s._tick()  # must not raise even though /dev/tty is unavailable

    def test_stop_swallows_oserror_when_writing_clear_line(self):
        with patch("builtins.open", side_effect=OSError("no tty")):
            s = Spinner()
            s.start()
            s.stop()  # the final clear-line write also hits the OSError branch
