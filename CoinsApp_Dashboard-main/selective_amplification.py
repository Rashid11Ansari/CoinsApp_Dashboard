from pathlib import Path
import pandas as pd


DATA_PATH = (
    Path(__file__).resolve().parent / "data" / "Product_features_summary_annotation.xlsx"
)

# Column definitions (must match header row 2 exactly)
HEPAR_PRODUCT_COL = "Hepar.comp.Ampoules..Bulk.mat.52324."
HEPAR_INGREDIENT_COLS = [
    "Avena.sativa",
    "Chelidonium.majus",
    "Cinchona.pubescens",
    "Cynara.scolymus",
    "Lycopodium.clavatum",
    "Silybum.marianum.",
    "Taraxacum.officinale",
    "Veratrum.album",
    "Colon.Suis.D4",
    "Duodenum.Suis.D4",
    "Hepar.Suis.D4",
    "Pankreas.Suis.D4",
    "Thymus.Suis.D4",
    "Vesica.Fellea.Suis.D4",
]

HEPEEL_PRODUCT_COL = "Hepeel.ampoule.solution..Bulk"
HEPEEL_INGREDIENT_COLS = [
    "Chelidonium.majus",
    "Cinchona.pubescens",
    "Citrullus.colocynthis.",
    "Lycopodium.clavatum",
    "Myristica.fragrans.",
    "Silybum.marianum.",
    "Veratrum.album",
]

AMPLIFIED_THRESHOLD = 3.0
ATTENUATED_THRESHOLD = 0.333


def ensure_columns(frame: pd.DataFrame, required: list[str]) -> None:
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def compute_ratio_and_state(
    frame: pd.DataFrame, product_col: str, ingredient_cols: list[str]
) -> tuple[pd.Series, pd.Series]:
    ensure_columns(frame, [product_col, *ingredient_cols])

    max_ing = frame[ingredient_cols].max(axis=1, skipna=True)
    safe_divisor = max_ing.replace(0, pd.NA)
    ratio = frame[product_col] / safe_divisor

    amplified = ratio.ge(AMPLIFIED_THRESHOLD)
    attenuated = ratio.le(ATTENUATED_THRESHOLD) & max_ing.gt(0)

    state = pd.Series("Unchanged", index=frame.index)
    state = state.mask(attenuated, "Attenuated")
    state = state.mask(amplified, "Amplified")

    return ratio, state


def main() -> None:
    df = pd.read_excel(DATA_PATH, sheet_name="Sheet1", header=1)
    ensure_columns(df, ["feature"])

    hepar_ratio, hepar_state = compute_ratio_and_state(
        df, HEPAR_PRODUCT_COL, HEPAR_INGREDIENT_COLS
    )
    hepeel_ratio, hepeel_state = compute_ratio_and_state(
        df, HEPEEL_PRODUCT_COL, HEPEEL_INGREDIENT_COLS
    )

    result = pd.DataFrame(
        {
            "feature": df["feature"],
            "hepar_ratio": hepar_ratio,
            "hepar_state": hepar_state,
            "hepeel_ratio": hepeel_ratio,
            "hepeel_state": hepeel_state,
        }
    )

    print("Hepar counts:")
    print(hepar_state.value_counts())
    print("\nHepeel counts:")
    print(hepeel_state.value_counts())

    amplified_features = result.loc[
        result["hepar_state"] == "Amplified", "feature"
    ].head(5)
    print("\nFirst 5 amplified feature IDs for Hepar:")
    print(amplified_features.to_list())

    print("\nResult preview:")
    print(result.head())


if __name__ == "__main__":
    main()

