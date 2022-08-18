from dynaconf.utils import DynaconfDict

from merino.flags import FeatureFlags

mocked_settings = DynaconfDict(
    {
        "flags": {
            "test-enabled": {"scheme": "random", "enabled": 1},
            "test-not-enabled": {"scheme": "random", "enabled": 0},
        }
    }
)


def test_enabled():
    flags = FeatureFlags(mocked_settings)
    assert flags.is_enabled("test-enabled") is True


def test_not_enabled():
    flags = FeatureFlags(mocked_settings)
    assert flags.is_enabled("test-not-enabled") is False
