"""tooldex/_spinner.py — terminal spinner shown during discovery ("tooldexing  3s")."""
import threading
import time


class Spinner:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._started = False

    def _tick(self):
        try:
            tty = open("/dev/tty", "w")
        except OSError:
            return
        start = time.monotonic()
        try:
            while not self._stop.is_set():
                s = int(time.monotonic() - start)
                tty.write(f"\r  tooldexing  {s}s ")
                tty.flush()
                time.sleep(0.25)
        finally:
            tty.close()

    def start(self):
        self._thread.start()
        self._started = True

    def stop(self):
        self._stop.set()
        if self._started:
            self._thread.join()
        try:
            with open("/dev/tty", "w") as tty:
                tty.write("\r" + " " * 30 + "\r")
                tty.flush()
        except OSError:
            pass
