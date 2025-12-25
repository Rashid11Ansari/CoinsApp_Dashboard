import pandas as pd

from app import build_product_only_df, build_component_only_df


def _make_test_data():
    """
    Build small synthetic data frames to exercise Q4 and Q5 logic.

    Features layout:
      - f1: present in product, present in plant only
      - f2: present in product, present in animal only
      - f3: present in product, present in both plant and animal (common)
      - f4: present in product, absent in all components  -> Q5 (product-only)
      - f5: absent in product, present in plant only      -> Q4 (component-only, Plant)
      - f6: absent in product, present in animal only     -> Q4 (component-only, Animal)
    """
    summary_df = pd.DataFrame(
        {
            "feature": ["f1", "f2", "f3", "f4", "f5", "f6"],
            "plantA": [10, 0, 5, 0, 7, 0],
            "animalA": [0, 8, 5, 0, 0, 9],
            "name": ["feat1", "feat2", "feat3", "feat4", "feat5", "feat6"],
            "molecularFormula": ["MF1", "MF2", "MF3", "MF4", "MF5", "MF6"],
            "pubchemids": ["1", "2", "3", "4", "5", "6"],
            "NPC.pathway": ["p1", "p2", "p3", "p4", "p5", "p6"],
        }
    )

    product_df = pd.DataFrame(
        {
            "feature": ["f1", "f2", "f3", "f4"],
            "intensity": [100.0, 200.0, 300.0, 400.0],
            "Average.Rt.min.": [1.0, 2.0, 3.0, 4.0],
            "Average.Mz": [100.1, 200.2, 300.3, 400.4],
        }
    )

    groups = {
        "plant_cols": ["plantA"],
        "animal_cols": ["animalA"],
    }

    return product_df, summary_df, groups


def _test_q5_product_only():
    """Test Q5: features present in product but absent in all components."""
    prod_df, summary_df, groups = _make_test_data()

    df_q5 = build_product_only_df(prod_df, summary_df, groups)
    feats = set(df_q5["feature"].astype(str))

    # We expect only f4 to be product-only (no plant/animal signal).
    assert feats == {"f4"}, f"Q5 product-only features mismatch: got {feats}"

    # Check that annotation columns have been merged in.
    for col in ["name", "molecularFormula", "pubchemids", "NPC.pathway"]:
        assert col in df_q5.columns, f"Missing annotation column '{col}' in Q5 output"


def _test_q4_component_only():
    """Test Q4: features present in components but absent in the final product."""
    prod_df, summary_df, groups = _make_test_data()
    prod_ids = set(prod_df["feature"].astype(str))

    df_q4 = build_component_only_df(prod_ids, summary_df, groups)
    feats = set(df_q4["feature"].astype(str))

    # We expect f5 (plant only) and f6 (animal only) to be component-only.
    expected = {"f5", "f6"}
    assert feats == expected, f"Q4 component-only features mismatch: got {feats}"

    # Check source classification.
    source_map = dict(zip(df_q4["feature"].astype(str), df_q4["source"]))
    assert source_map["f5"] == "Plant", f"Expected f5 to be Plant, got {source_map['f5']}"
    assert source_map["f6"] == "Animal", f"Expected f6 to be Animal, got {source_map['f6']}"

    # Check max_component_intensity calculation.
    max_int_map = dict(
        zip(df_q4["feature"].astype(str), df_q4["max_component_intensity"])
    )
    assert max_int_map["f5"] == 7, f"Expected max intensity 7 for f5, got {max_int_map['f5']}"
    assert max_int_map["f6"] == 9, f"Expected max intensity 9 for f6, got {max_int_map['f6']}"


def run_tests() -> None:
    """Run all Q4/Q5-related tests."""
    print("Running Q5 (product-only) tests...")
    _test_q5_product_only()
    print("Running Q4 (component-only) tests...")
    _test_q4_component_only()
    print("All Q4/Q5 feature tests passed!")


if __name__ == "__main__":
    run_tests()


