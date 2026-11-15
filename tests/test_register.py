import json

from reglens.gap import register as reg


def passage(n, text, source="crr3-consolidated"):
    return reg.Passage(f"c{n}", source, f"Art. {n}", f"CRR Art. {n}", "L1", "all", text)


def test_quote_check_normalises_whitespace_and_quotes():
    text = "The institution shall\nvalidate its ‘rating systems’ at least annually."
    assert reg.quote_in("validate its 'rating systems' at least annually", text)
    assert not reg.quote_in("validate its models every two years", text)
    assert not reg.quote_in("", text)


def test_batches_split_by_source_and_size():
    ps = [passage(1, "x" * 3000), passage(2, "x" * 3000), passage(3, "x" * 9000),
          passage(4, "x" * 300, source="eba-gl-dod")]
    sizes = [[p.chunk_id for p in b] for b in reg.batches(ps, max_tokens=2500)]
    assert sizes == [["c1", "c2"], ["c3"], ["c4"]]


def test_parse_batch_maps_passages_and_checks_quotes():
    batch = [passage(185, "Institutions shall regularly compare realised default rates with "
                          "estimated PDs for each grade.")]
    reply = json.dumps({"obligations": [
        {"passage": "P1", "actor": "institution", "topic": "pd", "strength": "shall",
         "obligation": "The institution shall compare realised default rates with PDs per grade.",
         "quote": "regularly compare realised default rates with estimated PDs",
         "validation_relevant": True},
        {"passage": "P1", "actor": "institution", "topic": "nonsense", "strength": "shall",
         "obligation": "Invented.", "quote": "not in the text"},
        {"passage": "P9", "obligation": "Unknown passage is dropped."},
    ]})
    obs = reg.parse_batch(batch, reply)
    assert len(obs) == 2
    assert obs[0].key == "CRR Art. 185" and obs[0].quote_ok and obs[0].topic == "pd"
    assert not obs[1].quote_ok and obs[1].topic == "other"
    reg.assign_ids(obs)
    assert len({o.id for o in obs}) == 2 and all(len(o.id) == 23 for o in obs)


def test_register_round_trip(tmp_path):
    obs = reg.parse_batch([passage(1, "shall do x")], json.dumps({"obligations": [
        {"passage": "P1", "obligation": "Do x.", "quote": "shall do x"}]}))
    reg.assign_ids(obs)
    path = tmp_path / "obligations.jsonl"
    reg.write_register(obs, path)
    assert reg.load_register(path) == obs
