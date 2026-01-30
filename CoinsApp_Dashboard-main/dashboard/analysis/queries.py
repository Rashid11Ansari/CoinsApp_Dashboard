"""Query layer for dashboard data analyses (OOP friendly)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

import pandas as pd

from dashboard.utils.identifiers import has_pubchem


# ---------- Base abstractions ----------


class BaseQuery(ABC):
    """Abstract base for all feature queries."""

    def __init__(self, summary_df: pd.DataFrame, groups: dict):
        self.summary_df = summary_df
        self.groups = groups

    @abstractmethod
    def run(self, *args, **kwargs) -> pd.DataFrame | dict:
        raise NotImplementedError


class OriginAwareQuery(BaseQuery):
    """Shared helpers for queries that require component-origin logic."""

    def present_in_any(
        self, feature_ids: Set[str], cols: List[str], threshold: float = 0
    ) -> Set[str]:
        """Return features (subset of feature_ids) present in ANY of the columns above threshold."""
        if not cols:
            return set()
        sub = self.summary_df[self.summary_df["feature"].isin(feature_ids)]
        mask = (sub[cols] > threshold).any(axis=1)
        return set(sub.loc[mask, "feature"].astype(str))

    def compute_origin_sets(
        self, product_df: pd.DataFrame, threshold: float = 0
    ) -> Dict[str, Set[str]]:
        """Classify product features into evidence-based sets (non-zero presence)."""
        prod_ids = set(product_df["feature"].astype(str).dropna())
        plant_ids = self.present_in_any(
            prod_ids, self.groups.get("plant_cols", []), threshold=threshold
        )
        animal_ids = self.present_in_any(
            prod_ids, self.groups.get("animal_cols", []), threshold=threshold
        )

        common = plant_ids.intersection(animal_ids)
        unique = prod_ids.difference(plant_ids.union(animal_ids))

        return {
            "All product features": prod_ids,
            "Common (plant+animal)": common,
            "Unique to product": unique,
        }


# ---------- Concrete queries ----------


class ProductOnlyQuery(OriginAwareQuery):
    """Q5: Features present in final product but absent in components."""

    def run(self, prod_df: pd.DataFrame) -> pd.DataFrame:
        origin_sets = self.compute_origin_sets(prod_df, threshold=0)
        ids = origin_sets["Unique to product"]
        dff = prod_df[prod_df["feature"].astype(str).isin(ids)].copy()

        annot_cols = [
            c
            for c in [
                "feature",
                "name",
                "molecularFormula",
                "pubchemids",
                "NPC.pathway",
            ]
            if c in self.summary_df.columns
        ]
        if annot_cols:
            annot = self.summary_df[annot_cols].drop_duplicates("feature")
            dff = dff.merge(annot, on="feature", how="left")

        keep = [
            c
            for c in [
                "feature",
                "intensity",
                "Average.Rt.min.",
                "Average.Mz",
                "name",
                "molecularFormula",
                "pubchemids",
                "NPC.pathway",
            ]
            if c in dff.columns
        ]
        return dff[keep].sort_values("intensity", ascending=False)


class ComponentOnlyQuery(BaseQuery):
    """Q4: Features present in raw components but absent in product."""

    def run(self, prod_feature_ids: Set[str]) -> pd.DataFrame:
        plant_cols = [c for c in self.groups.get("plant_cols", []) if c in self.summary_df.columns]
        animal_cols = [c for c in self.groups.get("animal_cols", []) if c in self.summary_df.columns]
        comp_cols = plant_cols + animal_cols

        if not comp_cols:
            return pd.DataFrame(columns=["feature", "source", "max_component_intensity"])

        comp_present_mask = (self.summary_df[comp_cols] > 0).any(axis=1)
        comp_present = self.summary_df.loc[comp_present_mask, "feature"].astype(str)

        comp_only_ids = set(comp_present) - set(map(str, prod_feature_ids))
        sdf = self.summary_df[self.summary_df["feature"].astype(str).isin(comp_only_ids)].copy()

        plant_present = (sdf[plant_cols] > 0).any(axis=1) if plant_cols else False
        animal_present = (sdf[animal_cols] > 0).any(axis=1) if animal_cols else False

        def _src(p, a):
            if p and a:
                return "Common (plant+animal)"
            if p:
                return "Plant"
            if a:
                return "Animal"
            return "Unknown"

        sdf["source"] = [_src(bool(p), bool(a)) for p, a in zip(plant_present, animal_present)]
        sdf["max_component_intensity"] = sdf[comp_cols].max(axis=1)

        keep = [
            c
            for c in [
                "feature",
                "source",
                "max_component_intensity",
                "Average.Rt.min.",
                "Average.Mz",
                "name",
                "molecularFormula",
                "pubchemids",
                "NPC.pathway",
            ]
            if c in sdf.columns
        ]
        return sdf[keep].sort_values("max_component_intensity", ascending=False)


class ComponentContributionQuery(BaseQuery):
    """Q6: Sum product intensities for features present in each component."""

    def run(self, prod_df: pd.DataFrame) -> pd.DataFrame:
        plant_cols = [c for c in self.groups.get("plant_cols", []) if c in self.summary_df.columns]
        animal_cols = [c for c in self.groups.get("animal_cols", []) if c in self.summary_df.columns]
        comp_cols = plant_cols + animal_cols

        if not comp_cols or "feature" not in self.summary_df.columns:
            return pd.DataFrame(columns=["component", "source", "product_intensity_sum", "fraction_of_total"])

        merged = prod_df[["feature", "intensity"]].merge(
            self.summary_df[["feature"] + comp_cols], on="feature", how="left"
        )

        rows: list[dict] = []
        for col in comp_cols:
            if col not in merged.columns:
                continue
            mask = merged[col] > 0
            contrib = float(merged.loc[mask, "intensity"].sum())
            if contrib <= 0:
                continue
            source = "Plant" if col in plant_cols else "Animal"
            rows.append(
                {
                    "component": str(col),
                    "source": source,
                    "product_intensity_sum": contrib,
                }
            )

        if not rows:
            return pd.DataFrame(columns=["component", "source", "product_intensity_sum", "fraction_of_total"])

        df = pd.DataFrame(rows)
        total = float(df["product_intensity_sum"].sum())
        if total > 0:
            df["fraction_of_total"] = df["product_intensity_sum"] / total
        else:
            df["fraction_of_total"] = 0.0

        return df.sort_values("product_intensity_sum", ascending=False)


class EnrichmentQuery(BaseQuery):
    """Q7 helper: enrichment ratio for product features present in components."""

    def run(self, prod_df: pd.DataFrame, min_component_intensity: float = 0.0) -> pd.DataFrame:
        plant_cols = [c for c in self.groups.get("plant_cols", []) if c in self.summary_df.columns]
        animal_cols = [c for c in self.groups.get("animal_cols", []) if c in self.summary_df.columns]
        comp_cols = plant_cols + animal_cols

        if "feature" not in self.summary_df.columns or not comp_cols:
            return pd.DataFrame(
                columns=[
                    "feature",
                    "intensity",
                    "max_component_intensity",
                    "enrichment_ratio",
                    "source",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                ]
            )

        annot_cols = [
            c for c in ["feature", "name", "molecularFormula", "pubchemids"] if c in self.summary_df.columns
        ]

        merged = prod_df[["feature", "intensity"]].merge(
            self.summary_df[["feature"] + comp_cols + [c for c in annot_cols if c != "feature"]],
            on="feature",
            how="left",
        )

        merged["max_component_intensity"] = merged[comp_cols].max(axis=1)
        dff = merged[merged["max_component_intensity"] > float(min_component_intensity)].copy()
        if dff.empty:
            return dff

        plant_present = (dff[plant_cols] > 0).any(axis=1) if plant_cols else False
        animal_present = (dff[animal_cols] > 0).any(axis=1) if animal_cols else False

        def _src(p, a):
            if p and a:
                return "Common (plant+animal)"
            if p:
                return "Plant"
            if a:
                return "Animal"
            return "Unknown"

        dff["source"] = [_src(bool(p), bool(a)) for p, a in zip(plant_present, animal_present)]
        dff["enrichment_ratio"] = dff["intensity"] / dff["max_component_intensity"]

        keep = [
            c
            for c in [
                "feature",
                "intensity",
                "max_component_intensity",
                "enrichment_ratio",
                "source",
                "name",
                "molecularFormula",
                "pubchemids",
            ]
            if c in dff.columns
        ]
        return dff[keep].sort_values("enrichment_ratio", ascending=False)


class AmplificationQuery(EnrichmentQuery):
    """Q8: classify amplification vs attenuation using enrichment ratios."""

    def run(
        self,
        prod_df: pd.DataFrame,
        min_component_intensity: float = 0.0,
        amp_ratio: float = 3.0,
        att_ratio: float = 3.0,
    ) -> pd.DataFrame:
        df = super().run(prod_df, min_component_intensity=min_component_intensity).copy()
        if df.empty or "enrichment_ratio" not in df.columns:
            return df

        er = df["enrichment_ratio"]
        amp_mask = er >= float(amp_ratio)
        att_mask = er <= 1.0 / float(att_ratio) if float(att_ratio) > 0 else False

        state = pd.Series("Neutral", index=df.index)
        state[amp_mask] = "Amplified"
        state[att_mask] = "Attenuated"
        df["state"] = state

        order_val = er.copy()
        order_val[att_mask] = 1.0 / er[att_mask].replace(0, pd.NA)
        df["order_value"] = order_val

        return df.sort_values("order_value", ascending=False)


class ProductOverlapQuery(BaseQuery):
    """Q9: Compare the two products and classify overlaps."""

    def run(self, hepar_df: pd.DataFrame, hepeel_df: pd.DataFrame) -> pd.DataFrame:
        if "feature" not in hepar_df.columns or "feature" not in hepeel_df.columns:
            return pd.DataFrame(
                columns=[
                    "feature",
                    "group",
                    "Hepar_intensity",
                    "Hepeel_intensity",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                ]
            )

        hepar_ids = set(hepar_df["feature"].astype(str).dropna())
        hepeel_ids = set(hepeel_df["feature"].astype(str).dropna())

        shared_ids = hepar_ids.intersection(hepeel_ids)
        hepar_only_ids = hepar_ids.difference(hepeel_ids)
        hepeel_only_ids = hepeel_ids.difference(hepar_ids)

        rows: list[dict] = []
        for fid in hepar_only_ids:
            rows.append({"feature": fid, "group": "Hepar only"})
        for fid in hepeel_only_ids:
            rows.append({"feature": fid, "group": "Hepeel only"})
        for fid in shared_ids:
            rows.append({"feature": fid, "group": "Shared"})

        if not rows:
            return pd.DataFrame(
                columns=[
                    "feature",
                    "group",
                    "Hepar_intensity",
                    "Hepeel_intensity",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                ]
            )

        df = pd.DataFrame(rows)

        hepar_int = (
            hepar_df.groupby("feature")["intensity"].max().rename("Hepar_intensity")
            if "intensity" in hepar_df.columns
            else None
        )
        hepeel_int = (
            hepeel_df.groupby("feature")["intensity"].max().rename("Hepeel_intensity")
            if "intensity" in hepeel_df.columns
            else None
        )

        if hepar_int is not None:
            df = df.merge(hepar_int, left_on="feature", right_index=True, how="left")
        if hepeel_int is not None:
            df = df.merge(hepeel_int, left_on="feature", right_index=True, how="left")

        annot_cols = [
            c for c in ["feature", "name", "molecularFormula", "pubchemids"] if c in self.summary_df.columns
        ]
        if annot_cols:
            annot = self.summary_df[annot_cols].drop_duplicates("feature")
            df = df.merge(annot, on="feature", how="left")

        return df


class ProductDiffQuery(BaseQuery):
    """Q10: Differential features between Hepar and Hepeel."""

    def run(
        self,
        hepar_df: pd.DataFrame,
        hepeel_df: pd.DataFrame,
        min_total_intensity: float = 0.0,
    ) -> pd.DataFrame:
        if "feature" not in hepar_df.columns or "feature" not in hepeel_df.columns:
            return pd.DataFrame(
                columns=[
                    "feature",
                    "Hepar_intensity",
                    "Hepeel_intensity",
                    "log2_fc",
                    "direction",
                    "driver",
                    "name",
                    "molecularFormula",
                    "pubchemids",
                ]
            )

        hepar_int = (
            hepar_df.groupby("feature")["intensity"].max().rename("Hepar_intensity")
            if "intensity" in hepar_df.columns
            else None
        )
        hepeel_int = (
            hepeel_df.groupby("feature")["intensity"].max().rename("Hepeel_intensity")
            if "intensity" in hepeel_df.columns
            else None
        )

        all_features = set(hepar_df["feature"].astype(str).dropna()).union(
            set(hepeel_df["feature"].astype(str).dropna())
        )
        df = pd.DataFrame({"feature": list(all_features)}).set_index("feature")

        if hepar_int is not None:
            df = df.join(hepar_int, how="left")
        else:
            df["Hepar_intensity"] = 0.0
        if hepeel_int is not None:
            df = df.join(hepeel_int, how="left")
        else:
            df["Hepeel_intensity"] = 0.0

        df[["Hepar_intensity", "Hepeel_intensity"]] = df[["Hepar_intensity", "Hepeel_intensity"]].fillna(0.0)

        df["total_intensity"] = df["Hepar_intensity"] + df["Hepeel_intensity"]
        if min_total_intensity is not None and float(min_total_intensity) > 0:
            df = df[df["total_intensity"] >= float(min_total_intensity)].copy()
            if df.empty:
                df = df.reset_index()
                return df

        df["intensity_diff"] = df["Hepar_intensity"] - df["Hepeel_intensity"]

        def _direction(v: float) -> str:
            if v > 0:
                return "Hepar higher"
            if v < 0:
                return "Hepeel higher"
            return "Similar"

        df["direction"] = df["intensity_diff"].apply(_direction)

        plant_cols = [c for c in self.groups.get("plant_cols", []) if c in self.summary_df.columns]
        animal_cols = [c for c in self.groups.get("animal_cols", []) if c in self.summary_df.columns]
        comp_cols = plant_cols + animal_cols

        driver_series = pd.Series("Unknown", index=df.index)
        plant_sum_series = pd.Series(0.0, index=df.index)
        animal_sum_series = pd.Series(0.0, index=df.index)
        plant_detail_series = pd.Series("", index=df.index)
        animal_detail_series = pd.Series("", index=df.index)
        if comp_cols:
            comp_agg = (
                self.summary_df[["feature"] + comp_cols].drop_duplicates("feature").set_index("feature")
            )
            comp_agg = comp_agg.reindex(df.index).fillna(0.0)

            plant_sum = comp_agg[plant_cols].sum(axis=1) if plant_cols else pd.Series(0.0, index=comp_agg.index)
            animal_sum = comp_agg[animal_cols].sum(axis=1) if animal_cols else pd.Series(0.0, index=comp_agg.index)

            def _detail(row, cols):
                # return up to 7 non-zero entries as "col=value" sorted by value desc
                items = []
                for c in cols:
                    v = row.get(c, 0.0)
                    try:
                        v_float = float(v)
                    except Exception:
                        v_float = 0.0
                    if v_float and v_float != 0.0:
                        items.append((c, v_float))
                items = sorted(items, key=lambda x: x[1], reverse=True)
                items = items[:7]
                return "; ".join([f"{k}={int(v) if v.is_integer() else round(v,2)}" for k, v in items])

            plant_detail_series = pd.Series(
                [_detail(row, plant_cols) for _, row in comp_agg.iterrows()],
                index=comp_agg.index,
            )
            animal_detail_series = pd.Series(
                [_detail(row, animal_cols) for _, row in comp_agg.iterrows()],
                index=comp_agg.index,
            )

            plant_sum_series = plant_sum
            animal_sum_series = animal_sum

            def _driver(p, a) -> str:
                if p <= 0 and a <= 0:
                    return "Unknown"
                if p > a * 1.5:
                    return "Plant-dominated"
                if a > p * 1.5:
                    return "Animal-dominated"
                return "Mixed"

            driver_series = pd.Series(
                [_driver(float(p), float(a)) for p, a in zip(plant_sum, animal_sum)],
                index=df.index,
            )

        df["driver"] = driver_series
        df["plant_sum"] = plant_sum_series
        df["animal_sum"] = animal_sum_series
        df["plant_detail"] = plant_detail_series
        df["animal_detail"] = animal_detail_series
        df["plant_animal_diff"] = df["plant_sum"] - df["animal_sum"]
        df = df.reset_index()

        annot_cols = [c for c in ["feature", "name", "molecularFormula", "pubchemids"] if c in self.summary_df.columns]
        if annot_cols:
            annot = self.summary_df[annot_cols].drop_duplicates("feature")
            df = df.merge(annot, on="feature", how="left")

        return df


class OriginSetQuery(OriginAwareQuery):
    """Reusable query that returns origin sets for a product dataframe."""

    def run(self, prod_df: pd.DataFrame, threshold: float = 0.0) -> Dict[str, Set[str]]:
        return self.compute_origin_sets(prod_df, threshold=threshold)


# ---------- Registry ----------


@dataclass
class QueryRegistry:
    """Convenience wrapper to access all query objects."""

    summary_df: pd.DataFrame
    groups: dict

    def __post_init__(self) -> None:
        self.origin_sets = OriginSetQuery(self.summary_df, self.groups)
        self.product_only = ProductOnlyQuery(self.summary_df, self.groups)
        self.component_only = ComponentOnlyQuery(self.summary_df, self.groups)
        self.component_contrib = ComponentContributionQuery(self.summary_df, self.groups)
        self.enrichment = EnrichmentQuery(self.summary_df, self.groups)
        self.amplification = AmplificationQuery(self.summary_df, self.groups)
        self.product_overlap = ProductOverlapQuery(self.summary_df, self.groups)
        self.product_diff = ProductDiffQuery(self.summary_df, self.groups)

    def filter_pubchem(self, df: pd.DataFrame, only_pubchem_vals) -> pd.DataFrame:
        """Apply optional PubChem filter uniformly."""
        if "only" in (only_pubchem_vals or []):
            if "pubchemids" in df.columns:
                return df[df["pubchemids"].apply(has_pubchem)].copy()
            return df.iloc[0:0].copy()
        return df


