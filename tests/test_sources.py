from reglens.sources import load_sources


def test_registry_loads_and_is_valid():
    sources = load_sources()
    ids = {s.id for s in sources}
    assert "crr3-consolidated" in ids
    assert all(s.reuse for s in sources)
    # Every unresolved URL must be flagged for verification.
    assert all(s.verify for s in sources if s.url is None)
