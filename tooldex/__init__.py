from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tooldex")
except PackageNotFoundError:
    __version__ = "unknown"
