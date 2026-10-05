"""Settings wrapper kept from the Python 2 days for backwards compatibility.

Note: LegacyConfig is NOT a dict. It has its own has_key() and no __contains__.
"""


class LegacyConfig(object):
    def __init__(self, values):
        self._values = dict(values)

    def has_key(self, key):
        return key in self._values

    def __getitem__(self, key):
        return self._values[key]

    def get(self, key, default=None):
        if self.has_key(key):
            return self[key]
        return default


def load_flags(cfg):
    flags = {"debug": False}
    if cfg.has_key("debug"):
        flags["debug"] = bool(cfg["debug"])
    return flags
