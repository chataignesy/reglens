from reglens.retrieve.glossary import expand_query


def test_expands_known_terms_once():
    q = expand_query("Which LGD applies under F-IRB? And under foundation IRB?")
    assert "own estimates of LGD" in q
    assert q.count("Article 161(1)") == 1  # same entry matched twice, added once


def test_word_boundaries():
    assert expand_query("What does the SME supporting factor do?") == (
        "What does the SME supporting factor do?"
    )
    assert "conversion factor" in expand_query("How are CCFs estimated?")
    assert "commercial immovable property" not in expand_query("Is CREDIT risk covered?")
