"""tooldex/_silenced.py — run a sync/async call with stdout+stderr redirected to /dev/null."""
import os


def silenced(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) with stdout+stderr redirected to /dev/null, then restore them."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved_out, saved_err = os.dup(1), os.dup(2)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        return fn(*args, **kwargs)
    finally:
        os.dup2(saved_out, 1); os.close(saved_out)
        os.dup2(saved_err, 2); os.close(saved_err)
