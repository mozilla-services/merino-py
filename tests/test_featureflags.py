from merino.featureflags import FeatureFlags, session_id_context


def test_missing():
    flags = FeatureFlags()
    assert flags.is_enabled("test-missing") is False


def test_no_scheme():
    flags = FeatureFlags()
    assert flags.is_enabled("test-no-scheme") is False


def test_enabled():
    flags = FeatureFlags()
    assert flags.is_enabled("test-enabled") is True


def test_not_enabled():
    flags = FeatureFlags()
    assert flags.is_enabled("test-not-enabled") is False


def test_enabled_perc():
    flags = FeatureFlags()
    assertions = {
        b"\x00\x00\x00\x00": True,
        b"\xff\xff\xff\xff": False,
    }

    for bid, test in assertions.items():
        assert flags.is_enabled("test-perc-enabled", bucket_for=bid) is test


def test_enabled_perc_session():
    flags = FeatureFlags()
    assertions = {
        "000": True,
        "fff": False,
    }

    for bid, test in assertions.items():
        session_id_context.set(bid)
        assert flags.is_enabled("test-perc-enabled-session") is test
