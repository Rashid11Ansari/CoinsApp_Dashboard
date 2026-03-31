from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
import json

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


def _match_cols_by_norm(component_cols: list[str], desired: list[str]) -> list[str]:
    """Match desired column names to actual summary columns via normalized names."""
    desired_norm = [_norm_component_name(x) for x in desired]
    # map normalized -> original column(s)
    norm_to_cols: dict[str, list[str]] = {}
    for c in component_cols:
        norm_to_cols.setdefault(_norm_component_name(c), []).append(c)

    out: list[str] = []
    seen: set[str] = set()
    for dn in desired_norm:
        for c in norm_to_cols.get(dn, []):
            if c not in seen:
                out.append(c)
                seen.add(c)
                break
    return out
def _load_components_config(base: Path) -> dict:
    """Load component definitions from data/components_config.json if present."""
    cfg_path = base / "components_config.json"
    if not cfg_path.exists():
        return {}
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _list_from_cfg(cfg: dict, key: str, default: list[str]) -> list[str]:
    v = cfg.get(key)
    if isinstance(v, list) and all(isinstance(x, str) for x in v) and len(v) > 0:
        return v
    return default

def _classify_component_columns_by_lists(
    component_cols: list[str],
    hepar_components: list[str],
    hepeel_components: list[str],
    plant_components: list[str],
    animal_components: list[str],
    hepar_plant_components: list[str],
    hepar_animal_components: list[str],
    hepeel_plant_components: list[str],
    hepeel_animal_components: list[str],
) -> dict:
    """Classify component columns using project-authoritative lists."""

    hepar_cols = _match_cols_by_norm(component_cols, hepar_components)
    hepeel_cols = _match_cols_by_norm(component_cols, hepeel_components)

    plant_cols = _match_cols_by_norm(component_cols, plant_components)
    animal_cols = _match_cols_by_norm(component_cols, animal_components)

    hepar_plant_cols = _match_cols_by_norm(component_cols, hepar_plant_components)
    hepar_animal_cols = _match_cols_by_norm(component_cols, hepar_animal_components)

    hepeel_plant_cols = _match_cols_by_norm(component_cols, hepeel_plant_components)
    hepeel_animal_cols = _match_cols_by_norm(component_cols, hepeel_animal_components)

    known = set(plant_cols + animal_cols)
    unknown_cols = [c for c in component_cols if c not in known]

    return {
        "hepar_component_cols": hepar_cols,
        "hepeel_component_cols": hepeel_cols,
        "plant_cols": plant_cols,
        "animal_cols": animal_cols,
        "unknown_component_cols": unknown_cols,
        "hepar_plant_cols": hepar_plant_cols,
        "hepar_animal_cols": hepar_animal_cols,
        "hepeel_plant_cols": hepeel_plant_cols,
        "hepeel_animal_cols": hepeel_animal_cols,
    }
    

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
                df.columns = [c.strip().strip('"') if isinstance(c, str) else c for c in df.columns]
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
            df.columns = [c.strip().strip('"') if isinstance(c, str) else c for c in df.columns]
            return df

    raise ValueError("Could not find a 'feature' column in the summary annotation file (Excel headers tried 0-3).")


def _build_component_groups(summary_df: pd.DataFrame) -> dict:
    """
    Detect candidate component intensity columns.
    IMPORTANT: We avoid pulling in annotation columns like probabilities/ranks by name.
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
        "product_features_merge_updated.txt",
        "product_features_merge_updated.tsv",
        "product_features_merge_updated.csv",
        "product_feature_merge_updated.txt",
        "product_feature_merge_updated.tsv",
        "product_feature_merge_updated.csv",
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

    cfg = _load_components_config(base)
    if not cfg:
        raise FileNotFoundError(
            f"Missing or invalid components_config.json in data folder: {base}. "
            "Create data/components_config.json with keys: "
            "hepar_components, hepeel_components, plant_components, animal_components, "
            "hepar_plant_components, hepar_animal_components, hepeel_plant_components, hepeel_animal_components."
        )

    def _require_list(key: str) -> list[str]:
        v = cfg.get(key)
        if isinstance(v, list) and all(isinstance(x, str) for x in v) and len(v) > 0:
            return v
        raise ValueError(f"components_config.json missing/invalid key: {key}")

    hepar_components = _require_list("hepar_components")
    hepeel_components = _require_list("hepeel_components")
    plant_components = _require_list("plant_components")
    animal_components = _require_list("animal_components")

    hepar_plant_components = _require_list("hepar_plant_components")
    hepar_animal_components = _require_list("hepar_animal_components")

    hepeel_plant_components = _require_list("hepeel_plant_components")
    # allow empty list for hepeel_animal_components
    hepeel_animal_components = cfg.get("hepeel_animal_components", [])
    if not isinstance(hepeel_animal_components, list):
        hepeel_animal_components = []

    # fixed classification based on project column lists
    class_groups = _classify_component_columns_by_lists(
        groups["component_cols"],
        hepar_components=hepar_components,
        hepeel_components=hepeel_components,
        plant_components=plant_components,
        animal_components=animal_components,
        hepar_plant_components=hepar_plant_components,
        hepar_animal_components=hepar_animal_components,
        hepeel_plant_components=hepeel_plant_components,
        hepeel_animal_components=hepeel_animal_components,
    )

    cols_to_num = set(class_groups["hepar_component_cols"] + class_groups["hepeel_component_cols"])

    for c in cols_to_num:
        if c in summary.columns:
            summary[c] = pd.to_numeric(summary[c], errors="coerce").fillna(0)

    groups.update({
        **class_groups,
        "threshold_default": 0,
    })

    # optional: keep a small, clean debug print
    # print(f"DEBUG plant_cols={len(plant_cols)} animal_cols={len(animal_cols)} unknown_cols={len(unknown_cols)}")

    return {
        "Hepar": ProductData(name="Hepar", features=hepar_feat),
        "Hepeel": ProductData(name="Hepeel", features=hepeel_feat),
        "_summary": summary,
        "_groups": groups,
    }