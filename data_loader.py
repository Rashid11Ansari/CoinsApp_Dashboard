from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


DATA_ROOT = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class ProductData:
    name: str
    features: pd.DataFrame


# ----------------------------
# Normalization + authority lists
# ----------------------------

def _norm_component_name(s: str) -> str:
    """
    Normalize component names so:
      - 'Colon.Suis.D4' -> 'colon suis'
      - 'Colon suis' -> 'colon suis'
      - 'Avena.sativa' -> 'avena sativa'
    """
    s = str(s).strip().lower()
    s = s.replace(".", " ").replace("_", " ")
    s = re.sub(r"\bd\d+\b", "", s)          # remove potency tokens like d4, d10
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_component_authority_xlsx(path: Path) -> tuple[set[str], set[str]]:
    """
    Read Hepar_Hepeel.xlsx to get authoritative:
      - plant component names (from 'Plant coponents' sheet)
      - animal component names (from 'Hepar comp.' sheet, rows containing 'suis')
    """
    xls = pd.read_excel(path, sheet_name=None)

    # --- plants ---
    plant_sheet = next((k for k in xls.keys() if k.strip().lower() in {"plant coponents", "plant components"}), None)
    plant_names: set[str] = set()
    if plant_sheet:
        dfp = xls[plant_sheet]
        plant_col = next(
            (c for c in dfp.columns if str(c).strip().lower() in {"plant component", "plant components"}),
            dfp.columns[0],
        )
        for v in dfp[plant_col].dropna().tolist():
            plant_names.add(_norm_component_name(v))

    # --- animals (suis ingredients) ---
    hepar_comp_sheet = next((k for k in xls.keys() if k.strip().lower() == "hepar comp."), None)
    animal_names: set[str] = set()
    if hepar_comp_sheet:
        dfh = xls[hepar_comp_sheet]
        med_col = dfh.columns[0]
        for m in dfh[med_col].dropna().astype(str).tolist():
            if "suis" in m.lower():
                animal_names.add(_norm_component_name(m))

    return plant_names, animal_names


def _classify_component_columns_by_authority(
    component_cols: list[str],
    plant_names_norm: set[str],
    animal_names_norm: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    STRICT classification:
      - animal_cols: normalized name matches animal list OR contains 'suis'
      - plant_cols: normalized name matches plant list
      - unknown_cols: everything else (ignored for origin analysis)
    """
    plant_cols: list[str] = []
    animal_cols: list[str] = []
    unknown_cols: list[str] = []

    for col in component_cols:
        n = _norm_component_name(col)
        if n in animal_names_norm or "suis" in n:
            animal_cols.append(col)
        elif n in plant_names_norm:
            plant_cols.append(col)
            print(plant_cols)
        else:
            unknown_cols.append(col)

    return plant_cols, animal_cols, unknown_cols
    

# ----------------------------
# File readers
# ----------------------------

def _read_features_txt(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")

    # numeric columns
    for col in ["intensity", "Average.Rt.min.", "Average.Mz"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # log intensity
    if "intensity" in df.columns:
        df["log10_intensity"] = df["intensity"].clip(lower=1).apply(lambda x: math.log10(x))

    # normalize feature id
    if "feature" in df.columns:
        df["feature"] = df["feature"].astype(str)

    return df


def _read_summary_annotation_txt(path: Path) -> pd.DataFrame:
    """Read the summary+annotation table.

    Supports:
      - .xlsx/.xls (Excel)
      - .txt/.tsv (tab-delimited)
      - .csv (comma-delimited)

    Must contain a 'feature' column.
    """
    suffix = path.suffix.lower()

    # ---- delimited text ----
    if suffix in {".txt", ".tsv", ".csv", ".text"}:
        # Some exports are not truly tab-delimited; try to sniff delimiter.
        # Also handle UTF-8 BOM via utf-8-sig.
        sample = ""
        try:
            sample = path.read_text(encoding="utf-8-sig", errors="replace")[:50_000]
        except Exception:
            pass

        # Candidate separators: tab, comma, semicolon, pipe
        seps = ["\t", ",", ";", "|"]
        # Default based on extension
        default_sep = "\t" if suffix in {".txt", ".tsv", ".text"} else ","

        def _try_read(sep: str, hdr: int) -> pd.DataFrame | None:
            try:
                df0 = pd.read_csv(path, sep=sep, header=hdr, engine="python", encoding="utf-8-sig")
                return df0
            except Exception:
                return None

        # Prefer the sep that yields the most columns (a good proxy for correct delimiter)
        best_df = None
        best_cols = 0
        best_sep = None
        best_hdr = None

        for hdr in [0, 1, 2, 3]:
            # If we have sample text, choose a likely sep by counting occurrences in the header line
            sep_order = seps
            if sample:
                header_line = sample.splitlines()[hdr] if len(sample.splitlines()) > hdr else sample.splitlines()[0]
                counts = {s: header_line.count(s) for s in seps}
                sep_order = sorted(seps, key=lambda s: counts[s], reverse=True)
                # Ensure default sep is tried early too
                if default_sep in sep_order:
                    sep_order.remove(default_sep)
                    sep_order.insert(0, default_sep)

            for sep in sep_order:
                df = _try_read(sep, hdr)
                if df is None:
                    continue
                # normalize column names
                df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]
                ncols = len(df.columns)
                if ncols > best_cols:
                    best_df, best_cols, best_sep, best_hdr = df, ncols, sep, hdr

        if best_df is None:
            raise ValueError("Failed to read the summary annotation text file with common delimiters.")

        df = best_df

        # exact match
        if "feature" in df.columns:
            df["feature"] = df["feature"].astype(str)
            return df

        # case-insensitive / common variants
        lower_map = {str(c).strip().lower(): c for c in df.columns}
        for key in ["feature", "feature_id", "featureid", "features", "id", "rowid", "row_id"]:
            if key in lower_map:
                df = df.rename(columns={lower_map[key]: "feature"})
                df["feature"] = df["feature"].astype(str)
                return df

        # substring match
        for c in df.columns:
            if "feature" in str(c).strip().lower():
                df = df.rename(columns={c: "feature"})
                df["feature"] = df["feature"].astype(str)
                return df

        # heuristic: first column looks like MS feature IDs
        if len(df.columns) >= 1:
            first = df.columns[0]
            s = df[first].astype(str)
            looks_like_feature = (
                s.str.match(r"^[A-Za-z]+_\d+", na=False).mean() >= 0.5
                or s.str.startswith("N_", na=False).mean() >= 0.5
            )
            if looks_like_feature:
                df = df.rename(columns={first: "feature"})
                df["feature"] = df["feature"].astype(str)
                return df

        # If still not found, raise with helpful debugging info
        preview_cols = list(df.columns)[:30]
        raise ValueError(
            "Could not find a 'feature' column in the summary annotation text file. "
            f"Detected sep={best_sep!r}, header={best_hdr}. "
            f"First columns: {preview_cols}"
        )

    # ---- Excel ----
    for hdr in [0, 1, 2, 3]:
        df = pd.read_excel(path, sheet_name=0, header=hdr)
        if "feature" in df.columns:
            df["feature"] = df["feature"].astype(str)
            df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]
            return df

    raise ValueError("Could not find a 'feature' column in the summary annotation file (Excel headers tried 0-3).")


def _build_component_groups(summary_df: pd.DataFrame) -> dict:
    """
    Detect candidate component intensity columns.
    IMPORTANT: We avoid pulling in annotation columns like probabilities/ranks by name.
    Then we will strictly filter plant/animal using the authority file anyway.
    """
    cols = [c for c in summary_df.columns if c != "feature"]

    # Exclude known annotation/meta columns (extend as needed)
    exclude_by_substring = [
        "probab", "score", "rank", "confidence", "sirius", "zodiac", "csi",
        "inchi", "inchikey", "smiles", "classyfire", "npc.",
        "overallfeaturequality", "structureperidrank", "xlogp",
        "pubchem", "links", "dbflags", "molecularformula", "adduct", "name",
    ]

    def is_excluded(c: str) -> bool:
        cl = str(c).lower()
        return any(sub in cl for sub in exclude_by_substring)

    candidate_cols = [c for c in cols if not is_excluded(c)]

    # Keep numeric-like columns among candidates
    component_cols: list[str] = []
    for c in candidate_cols:
        s = pd.to_numeric(summary_df[c], errors="coerce")
        if s.notna().mean() >= 0.05:  # at least 5% numeric
            component_cols.append(c)

    # Detect product columns (optional; useful for debugging)
    product_cols = {}
    for c in component_cols:
        cl = str(c).lower()
        if "hepar" in cl:
            product_cols["Hepar"] = c
        if "hepeel" in cl:
            product_cols["Hepeel"] = c

    return {
        "component_cols": component_cols,
        "product_cols": product_cols,
        "threshold_default": 0,
    }


# ----------------------------
# Main entry
# ----------------------------

def load_all(data_dir: str | Path | None = None) -> dict:
    base = Path(data_dir) if data_dir is not None else DATA_ROOT

    hepar_feat = _read_features_txt(base / "Hepar_features.txt")
    hepeel_feat = _read_features_txt(base / "Hepeel_features.txt")

    # summary/annotation table (file name may change)
    summary_candidates = [
        # newer merged summary files (names vary)
        "Product_features_merge_updated.txt",
        "Product_features_merge_updated.tsv",
        "Product_features_merge_updated.csv",

    ]

    summary_path = None
    for fname in summary_candidates:
        p = base / fname
        if p.exists():
            summary_path = p
            break

    if summary_path is None:
        existing = sorted([p.name for p in base.glob("*")])
        raise FileNotFoundError(
            "Could not find a summary/annotation file in the data folder. "
            f"Tried: {summary_candidates}. "
            f"Data folder: {base}. "
            f"Files present: {existing}"
        )

    summary = _read_summary_annotation_txt(summary_path)
    groups = _build_component_groups(summary)

    # authority lists
    plant_names_norm, animal_names_norm = _load_component_authority_xlsx(base / "Hepar_Hepeel.xlsx")

    # strict plant/animal cols
    plant_cols, animal_cols, unknown_cols = _classify_component_columns_by_authority(
        groups["component_cols"], plant_names_norm, animal_names_norm
    )

    # Convert ONLY these component cols to numeric once (performance + consistency)
    for c in set(plant_cols + animal_cols):
        if c in summary.columns:
            summary[c] = pd.to_numeric(summary[c], errors="coerce").fillna(0)

    groups.update({
        "plant_cols": plant_cols,
        "animal_cols": animal_cols,
        "unknown_component_cols": unknown_cols,
        "plant_names_norm": plant_names_norm,
        "animal_names_norm": animal_names_norm,
    })

    # optional: keep a small, clean debug print
    print(f"DEBUG plant_cols={len(plant_cols)} animal_cols={len(animal_cols)} unknown_cols={len(unknown_cols)}")

    return {
        "Hepar": ProductData(name="Hepar", features=hepar_feat),
        "Hepeel": ProductData(name="Hepeel", features=hepeel_feat),
        "_summary": summary,
        "_groups": groups,
    }