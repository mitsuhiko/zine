from importlib.metadata import version


def test_zine_can_be_imported():
    import zine

    assert zine.__version__ == "0.2-dev"


def test_distribution_metadata_is_installed():
    assert version("Zine") == "0.2.dev0"
