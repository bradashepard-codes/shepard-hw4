---
name: cocktail-batch-math
description: Scales a single-serving cocktail recipe to N servings, computes pre- and post-dilution ABV with a method-specific dilution model, checks target-ABV feasibility, and emits a printable batch card with moderation guidance. Use when a user asks to batch, scale, multiply, or pre-mix a cocktail for a party, event, or guest count, or when a target final-strength ABV must be hit deterministically.
---

# cocktail-batch-math

Batch-cocktail planning is half craft, half arithmetic. The craft (which spirit, which modifier, what flavor profile) is for the model. The arithmetic — scaling volumes, summing alcohol content, applying a dilution model, and checking whether a target ABV is even reachable — is for `scripts/batch_scale.py`. Models hallucinate ABV math; the script does not.

## When to use

Activate this skill when the user asks anything in this shape:

- "Scale this cocktail for 24 / 50 / 12 people."
- "Batch this for a party — what's the shopping list and final volume?"
- "What ABV does this end up at after stirring/shaking?"
- "Hit 18% ABV after dilution — is that achievable with this recipe?"
- "Pre-mix this so I can pour at the bar."
- "Convert this single-drink recipe to a 1.5L bottle of pre-batch."

Also appropriate when a recipe has been drafted earlier in conversation and the user wants to take it from "one serving" to "party-ready."

## When NOT to use

- Generic recipe ideation, flavor riffs, garnish brainstorming — that's prose, not math. Stay model-driven.
- Ingredient substitution recommendations (e.g., "what can I use instead of dry curaçao?") — flavor judgment, not arithmetic.
- Sourcing, pricing, or shopping logistics outside the recipe itself.
- Anything involving recommending alcohol to minors, encouraging excessive consumption, or producing a recipe whose explicit goal is rapid intoxication. Decline in line with normal Drinkmaster-style safety guidance.
- Non-cocktail dilution problems (e.g., chemistry-class mixing). The model assumes ice-melt dilution behavior.

## Inputs

The script reads a recipe as JSON. You can write the JSON yourself from the user's prose, or load from a file the user supplies.

```json
{
  "name": "Old Fashioned",
  "method": "stirred",
  "ingredients": [
    {"name": "Bourbon",            "volume_ml": 60,  "abv": 45},
    {"name": "Demerara syrup",     "volume_ml": 7.5, "abv": 0},
    {"name": "Angostura bitters",  "volume_ml": 1,   "abv": 44}
  ]
}
```

Field rules:

- `name` — required, non-empty string.
- `method` — one of `stirred` | `shaken` | `built` | `blended` | `none`. Drives the dilution factor (see `references/dilution-model.md`).
- `ingredients[].name` — required, non-empty.
- `ingredients[].volume_ml` (or `volume_oz`) — per-serving volume, > 0.
- `ingredients[].abv` — alcohol-by-volume %, in [0, 100]. Use 0 for syrups, juice, water.

CLI flags layered on top of the file:

- `--servings N` (required) — guest/serving count.
- `--method {stirred,shaken,built,blended,none}` — overrides recipe `method`.
- `--target-abv X` — optional final-ABV target; script flags infeasibility.
- `--units {ml,oz}` — output unit for the printed batch card. Default `ml`.

## Step-by-step

1. **Confirm the recipe.** If the user gave a recipe in prose, extract ingredients with volumes and ABVs. If an ABV is unknown, infer from typical category (whiskey ~40-45%, vermouth ~17%, amaro ~22%, juice/syrup 0%) and **note your inference in the response** so the user can override.
2. **Confirm scope.** Get `servings`, `method`, and (optionally) `target_abv`. Don't guess these — ask if missing.
3. **Write the recipe JSON.** Save it to a temporary path or under `references/examples/` if the user wants it preserved.
4. **Run the script:**
   ```bash
   python3 .agents/skills/cocktail-batch-math/scripts/batch_scale.py \
       <recipe.json> --servings <N> [--method ...] [--target-abv ...] [--units ml|oz]
   ```
5. **Pass through the script's report verbatim** as the deterministic core of your reply. Add a one- or two-line craft note above (style, garnish, glassware) and any safety/moderation guidance the script flagged.
6. **Handle the script's exit codes:**
   - `0` — success, just present the report.
   - `2` — input validation failed; show the script's stderr to the user and ask them to clarify.
   - `3` — target ABV infeasible; **do not** silently relax the target. Surface the script's reason and offer concrete adjustments (different method, lower target, raise spirit content).

## Output format

Lead with one short paragraph of craft context (glassware, garnish, finishing). Then paste the script's full Markdown report. Close with moderation/responsible-service guidance if the script flagged it, or if guest count and final ABV imply a strong serve.

Do **not** restate the script's numbers in prose — the table and bullets are the canonical output. Restating invites you to round inconsistently and undermines the determinism the script provides.

## Limitations

- The dilution model is approximate. Stirred ~25%, shaken ~50%, built ~15%, blended ~75%. Real dilution depends on ice quality, technique time, ambient temperature, and shaker style. See `references/dilution-model.md` for source. For competition or commercial work, measure directly.
- The script computes ABV by simple volumetric mixing. It does not model contraction (alcohol + water mix to slightly less than additive volume), which introduces ~0.5% volume error at typical cocktail strengths — well below the precision of bar pours.
- ABV inputs are trusted. If the user gives a wrong ABV, the math is correct but the answer is wrong. Always show your inferred ABVs back to the user.
- The "moderation" warning is a heuristic at 25%/30% post-dilution ABV thresholds. Adjust if the audience demands more conservative guidance.
- Method `none` (no ice contact yet) reports pre-dilution ABV as the final figure. That is correct for *bottled* batches that will be diluted later at service — make sure the user understands that's the assumption.

## Important checks

- Refuse to optimize for "fastest path to drunk," "highest ABV possible regardless of taste," or any prompt whose explicit framing is harm-leaning.
- If `target_abv` exceeds the recipe's pre-dilution ABV, the script returns `infeasible_above_max` — that is a hard physics constraint, not a tunable. Surface it directly.
- For very large batches (servings > ~50), add a prep-ahead note: scale dilution slightly down for bottled service, or batch separately and dilute at the bar.
