#!/usr/bin/env python3
"""
batch_scale.py — Deterministic batch-cocktail scaler with ABV math.

Given a single-serving recipe (ingredients + volumes + ABVs), a serving count,
and a preparation method, compute:

  - scaled per-ingredient volumes (rounded to a sensible bar-pour precision)
  - pre-dilution ABV of the batch
  - post-dilution ABV after the chosen method's expected water gain
  - final pre- and post-dilution volumes (total and per serving)
  - feasibility check against an optional target ABV
  - moderation flag for high-ABV outputs

Input is JSON. See references/examples/ for shape.

Exit codes:
  0  — success, report printed to stdout
  2  — input validation failed (bad schema, impossible values)
  3  — target_abv is infeasible given the recipe + method

This script is intentionally dependency-free (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

# Dilution model.
#
# Volume gain from ice melt during preparation, expressed as a fraction of the
# pre-dilution batch volume. Values are widely cited approximations (Dave Arnold,
# Liquid Intelligence, 2014); they are reasonable for planning purposes but not
# exact for any specific bar setup. See references/dilution-model.md.
DILUTION_FACTORS: dict[str, float] = {
    "stirred": 0.25,   # stirred over ice ~25% water gain
    "shaken": 0.50,    # shaken with ice ~50% water gain
    "built": 0.15,     # built/assembled in glass with ice, light dilution
    "blended": 0.75,   # blended with ice, heavy dilution
    "none": 0.0,       # batched dry/pre-mix, no ice contact yet
}

METHOD_DESCRIPTIONS: dict[str, str] = {
    "stirred": "Stirred over ice (e.g., martini, negroni)",
    "shaken": "Shaken with ice (e.g., margarita, daiquiri)",
    "built": "Built/assembled in the glass with ice (e.g., rum & coke, aperol spritz)",
    "blended": "Blended with ice (e.g., frozen drinks, smoothies)",
    "none": "Pre-batched with no ice contact (dilute at service)",
}

# ABV thresholds for moderation flag (final post-dilution ABV).
HIGH_ABV_WARN = 25.0
HIGH_ABV_STRONG = 30.0

ML_PER_OZ = 29.5735


@dataclass
class Ingredient:
    name: str
    volume_ml: float
    abv: float  # 0..100


@dataclass
class Recipe:
    name: str
    method: str
    ingredients: list[Ingredient]


def parse_recipe(data: dict[str, Any]) -> Recipe:
    """Validate and load a recipe dict. Raises ValueError on bad input."""
    if not isinstance(data, dict):
        raise ValueError("Recipe must be a JSON object.")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Recipe.name must be a non-empty string.")
    method = data.get("method", "stirred")
    if method not in DILUTION_FACTORS:
        raise ValueError(
            f"Recipe.method must be one of {sorted(DILUTION_FACTORS)}; got {method!r}."
        )
    raw_ings = data.get("ingredients")
    if not isinstance(raw_ings, list) or not raw_ings:
        raise ValueError("Recipe.ingredients must be a non-empty list.")

    ingredients: list[Ingredient] = []
    for i, raw in enumerate(raw_ings):
        if not isinstance(raw, dict):
            raise ValueError(f"ingredients[{i}] must be an object.")
        ing_name = raw.get("name")
        if not isinstance(ing_name, str) or not ing_name.strip():
            raise ValueError(f"ingredients[{i}].name must be a non-empty string.")
        # Accept volume_ml or volume_oz for convenience.
        if "volume_ml" in raw:
            vol_ml = _to_float(raw["volume_ml"], f"ingredients[{i}].volume_ml")
        elif "volume_oz" in raw:
            vol_ml = _to_float(raw["volume_oz"], f"ingredients[{i}].volume_oz") * ML_PER_OZ
        else:
            raise ValueError(f"ingredients[{i}] needs volume_ml or volume_oz.")
        if vol_ml <= 0:
            raise ValueError(f"ingredients[{i}].volume must be > 0 (got {vol_ml}).")
        abv = _to_float(raw.get("abv", 0), f"ingredients[{i}].abv")
        if abv < 0 or abv > 100:
            raise ValueError(f"ingredients[{i}].abv must be in [0, 100] (got {abv}).")
        ingredients.append(Ingredient(name=ing_name.strip(), volume_ml=vol_ml, abv=abv))
    return Recipe(name=name.strip(), method=method, ingredients=ingredients)


def _to_float(v: Any, label: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric (got {v!r}).")


def scale(recipe: Recipe, servings: int) -> list[Ingredient]:
    if servings < 1:
        raise ValueError("servings must be >= 1.")
    return [
        Ingredient(name=ing.name, volume_ml=ing.volume_ml * servings, abv=ing.abv)
        for ing in recipe.ingredients
    ]


def pre_dilution_abv(ings: list[Ingredient]) -> tuple[float, float]:
    """Return (total_volume_ml, abv_pct)."""
    total_volume = sum(i.volume_ml for i in ings)
    if total_volume == 0:
        return 0.0, 0.0
    alcohol = sum(i.volume_ml * (i.abv / 100.0) for i in ings)
    return total_volume, (alcohol / total_volume) * 100.0


def post_dilution(volume_ml: float, abv_pct: float, method: str) -> tuple[float, float]:
    factor = DILUTION_FACTORS[method]
    final_volume = volume_ml * (1.0 + factor)
    if final_volume == 0:
        return 0.0, 0.0
    final_abv = abv_pct * (volume_ml / final_volume)
    return final_volume, final_abv


def check_target(target_abv: float | None, pre_abv: float, post_abv: float) -> dict[str, Any]:
    if target_abv is None:
        return {"requested": None, "status": "n/a"}
    if target_abv <= 0 or target_abv > 100:
        raise ValueError("target_abv must be in (0, 100].")
    # Dilution can only lower ABV vs pre-dilution.
    if target_abv > pre_abv + 1e-6:
        return {
            "requested": target_abv,
            "status": "infeasible_above_max",
            "max_achievable": pre_abv,
            "reason": (
                f"Target {target_abv:.1f}% exceeds pre-dilution ABV {pre_abv:.1f}%. "
                "Dilution only lowers ABV; raise spirit content or lower target."
            ),
        }
    if abs(post_abv - target_abv) <= 1.0:
        return {"requested": target_abv, "status": "match", "delta": post_abv - target_abv}
    if post_abv < target_abv:
        return {
            "requested": target_abv,
            "status": "below_target",
            "reason": (
                f"Method's dilution drops ABV to {post_abv:.1f}%, below target {target_abv:.1f}%. "
                "Try a lighter method (e.g., 'built' instead of 'shaken')."
            ),
        }
    return {
        "requested": target_abv,
        "status": "above_target",
        "reason": (
            f"Even with method dilution, ABV is {post_abv:.1f}%, above target {target_abv:.1f}%. "
            "Lower spirit ratio, dilute further, or use a method with more dilution."
        ),
    }


def round_pour(ml: float, units: str) -> str:
    """Round to bar-friendly precision and format with unit suffix."""
    if units == "oz":
        oz = ml / ML_PER_OZ
        # Round to nearest 1/4 oz when small, else 1/2 oz.
        if oz < 1:
            return f"{round(oz * 4) / 4:.2f} oz"
        return f"{round(oz * 2) / 2:.1f} oz"
    return f"{round(ml)} ml"


def format_report(
    recipe: Recipe,
    servings: int,
    scaled: list[Ingredient],
    pre_vol: float,
    pre_abv: float,
    post_vol: float,
    post_abv: float,
    target_check: dict[str, Any],
    units: str,
) -> str:
    lines: list[str] = []
    lines.append(f"# {recipe.name} — batch for {servings}")
    lines.append("")
    lines.append(f"**Method:** {METHOD_DESCRIPTIONS[recipe.method]}  ")
    lines.append(f"**Dilution factor:** +{int(DILUTION_FACTORS[recipe.method] * 100)}% volume from ice melt")
    lines.append("")
    lines.append("## Scaled ingredients")
    lines.append("")
    lines.append("| Ingredient | Per drink | Batch total | ABV |")
    lines.append("|---|---|---|---|")
    for orig, big in zip(recipe.ingredients, scaled):
        per = round_pour(orig.volume_ml, units)
        tot = round_pour(big.volume_ml, units)
        lines.append(f"| {big.name} | {per} | {tot} | {big.abv:.0f}% |")
    lines.append("")
    lines.append("## Volume and ABV")
    lines.append("")
    lines.append(f"- **Pre-dilution batch volume:** {round_pour(pre_vol, units)}")
    lines.append(f"- **Pre-dilution ABV:** {pre_abv:.1f}%")
    lines.append(f"- **Post-dilution batch volume:** {round_pour(post_vol, units)}")
    lines.append(f"- **Post-dilution ABV (final, served):** {post_abv:.1f}%")
    lines.append(f"- **Per-serving final pour:** {round_pour(post_vol / servings, units)}")
    lines.append("")
    lines.append("## Target ABV check")
    lines.append("")
    if target_check["status"] == "n/a":
        lines.append("_No target ABV provided._")
    elif target_check["status"] == "match":
        delta = target_check["delta"]
        lines.append(f"Target {target_check['requested']:.1f}% met (Δ {delta:+.1f}%).")
    else:
        lines.append(f"**Status:** `{target_check['status']}`  ")
        lines.append(f"**Reason:** {target_check['reason']}")
    lines.append("")
    lines.append("## Moderation")
    lines.append("")
    if post_abv >= HIGH_ABV_STRONG:
        lines.append(
            f"⚠️ Final ABV is {post_abv:.1f}% — very strong. Recommend smaller serves, "
            "water alongside, and spaced pacing for guests."
        )
    elif post_abv >= HIGH_ABV_WARN:
        lines.append(
            f"Final ABV is {post_abv:.1f}% — on the strong side. Pair with food and water."
        )
    else:
        lines.append(f"Final ABV {post_abv:.1f}% is in a reasonable range for batched service.")
    lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    try:
        with open(args.recipe, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not read recipe JSON: {e}", file=sys.stderr)
        return 2

    try:
        recipe = parse_recipe(data)
        if args.method:
            if args.method not in DILUTION_FACTORS:
                raise ValueError(
                    f"--method must be one of {sorted(DILUTION_FACTORS)}; got {args.method!r}."
                )
            recipe.method = args.method
        scaled = scale(recipe, args.servings)
        pre_vol, pre_abv = pre_dilution_abv(scaled)
        post_vol, post_abv = post_dilution(pre_vol, pre_abv, recipe.method)
        target_check = check_target(args.target_abv, pre_abv, post_abv)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    report = format_report(
        recipe, args.servings, scaled, pre_vol, pre_abv, post_vol, post_abv,
        target_check, args.units,
    )
    print(report)

    if target_check["status"].startswith("infeasible"):
        return 3
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Batch-scale a cocktail recipe with ABV math.")
    p.add_argument("recipe", help="Path to recipe JSON file.")
    p.add_argument("--servings", type=int, required=True, help="Number of servings to batch.")
    p.add_argument(
        "--method",
        choices=sorted(DILUTION_FACTORS),
        help="Override recipe method.",
    )
    p.add_argument(
        "--target-abv",
        dest="target_abv",
        type=float,
        default=None,
        help="Optional target final ABV percent; script verifies feasibility.",
    )
    p.add_argument(
        "--units",
        choices=["ml", "oz"],
        default="ml",
        help="Output volume units (default ml).",
    )
    return p


if __name__ == "__main__":
    sys.exit(run(build_parser().parse_args()))
