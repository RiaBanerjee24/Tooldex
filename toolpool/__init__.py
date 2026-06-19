from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("toolpool")
except PackageNotFoundError:
    __version__ = "unknown"
