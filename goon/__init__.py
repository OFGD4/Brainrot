try:
    from app_info import APP_VERSION as __version__
except ImportError:  # pragma: no cover
    __version__ = "0.0.0"

APP_NAME = "BrainrotGoonMachine"
