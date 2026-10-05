from shop.legacy_config import LegacyConfig, load_flags


def test_get_with_default():
    cfg = LegacyConfig({"region": "eu"})
    assert cfg.get("region") == "eu"
    assert cfg.get("missing", "x") == "x"


def test_load_flags():
    assert load_flags(LegacyConfig({"debug": 1})) == {"debug": True}
    assert load_flags(LegacyConfig({})) == {"debug": False}
