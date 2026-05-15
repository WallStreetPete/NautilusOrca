"""Black Orca Capital — AI-native hedge fund research and trading platform."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("blackorca")
except PackageNotFoundError:  # editable / not installed
    __version__ = "0.0.0-dev"

__all__ = ["__version__"]
