from .config_loader import ConfigLoader

# NOTE: Loading config at import time preserves backward compatibility for
# modules that expect a populated CONFIG without calling a loader. If callers
# are updated to lazily fetch config, this eager load can be revisited.
CONFIG = ConfigLoader.load_config()
