import orbit_engine


def test_package_version_is_explicit() -> None:
    assert orbit_engine.__version__ == "0.1.0"
