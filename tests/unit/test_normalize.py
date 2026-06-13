from abi.autoplasm.normalize.abundance import tpm
from abi.autoplasm.normalize.plasmid_prediction import integrate_calls, normalize_prediction_rows


def test_integrate_majority_vote():
    calls = {
        "genomad": {"c1": True, "c2": False},
        "plasme": {"c1": True, "c2": True},
        "plasx": {"c1": False, "c2": False},
    }
    assert integrate_calls(calls, strategy="majority_vote") == {"c1": True, "c2": False}


def test_normalize_prediction_rows():
    rows = normalize_prediction_rows(
        sample_id="S1",
        contig_lengths={"c1": 1000},
        calls_by_tool={"genomad": {"c1": True}},
        strategy="single_tool",
    )
    assert rows[0]["sample_id"] == "S1"
    assert rows[0]["genomad_call"] is True
    assert rows[0]["final_plasmid_call"] is True


def test_tpm_sums_to_million():
    values = tpm({"a": 10, "b": 10}, {"a": 1000, "b": 1000})
    assert round(sum(values.values())) == 1_000_000
