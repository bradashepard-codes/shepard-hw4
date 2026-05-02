# shepard-hw4 — Reusable AI Skill

Coursework: build one narrowly scoped, reusable AI skill where a Python script is genuinely load-bearing.

**Skill:** `cocktail-batch-math` — scale a single-serving cocktail recipe to N servings, compute pre- and post-dilution ABV with a method-specific dilution model, and check whether a requested target final ABV is even physically achievable.

**Walkthrough video:** https://youtu.be/EKNvPq2XMnY

## Why this skill

Batch-cocktail planning is half craft, half arithmetic. The craft (which spirit, which modifier, what flavor profile, garnish, glassware) is the kind of judgment a model handles well. The arithmetic — multiplying volumes across a guest count, summing ABV-weighted alcohol, applying a dilution factor for stir vs shake vs build, and detecting when a target final ABV is physically impossible — is the kind of thing models reliably get *almost* right and occasionally get badly wrong. Wrong by 3% ABV looks identical in prose but ruins a party drink.

This skill draws a clean line: the model orchestrates (extract ingredients from the user's prose, infer typical ABVs, write craft notes, surface moderation guidance) and the script does the math (scaling, ABV math, dilution model, feasibility check). The output is deterministic and reproducible.

## Repository layout

```
shepard-hw4/
├── README.md
├── LICENSE
└── .agents/
    └── skills/
        └── cocktail-batch-math/
            ├── SKILL.md
            ├── scripts/
            │   └── batch_scale.py
            └── references/
                ├── dilution-model.md
                └── examples/
                    ├── old-fashioned.json
                    ├── margarita.json
                    └── aperol-spritz.json
```

## How to use

The skill is auto-discovered by Claude Code (or any agent that scans `.agents/skills/`) when you open a session at the repo root. Trigger it by asking the agent any cocktail-batching question — the description in `SKILL.md` carries the activation logic.

Example one-liner direct script use:

```sh
python3 .agents/skills/cocktail-batch-math/scripts/batch_scale.py \
    .agents/skills/cocktail-batch-math/references/examples/old-fashioned.json \
    --servings 24 --target-abv 30 --units oz
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0    | Success, report printed to stdout |
| 2    | Input validation failed (bad schema, impossible values) |
| 3    | Target ABV is infeasible given the recipe + method |

The agent uses the exit code to decide whether to surface the report verbatim, ask a clarifying question, or push back on an impossible request.

## What the script does

`scripts/batch_scale.py` reads a recipe JSON file describing one serving and produces a Markdown batch card:

1. **Validates the recipe** — required fields, ingredient volumes > 0, ABVs in [0, 100], known method.
2. **Scales each ingredient** by the serving count and rounds to bar-friendly precision.
3. **Computes pre-dilution ABV** as the volumetric mix of alcohol content across all ingredients.
4. **Applies a method-specific dilution factor** (stirred +25%, shaken +50%, built +15%, blended +75%, none 0%) — see `references/dilution-model.md` for the source of these numbers.
5. **Computes post-dilution ABV and final volume.**
6. **Checks against an optional target ABV**, distinguishing four cases: matched, below target (method dilutes too much), above target (method dilutes too little), or **infeasible** because the target exceeds the pre-dilution ceiling (a physics constraint — dilution can only lower ABV).
7. **Flags moderation** when post-dilution ABV crosses heuristic thresholds (25%, 30%).

The output is a single Markdown report the agent can drop into the conversation verbatim — there is no follow-up prose math the model needs to do.

## Three demo prompts

Use these (or paraphrase) when invoking the skill in Claude Code to verify activation and behavior.

### 1. Normal case

> Build me a batch of Old Fashioneds for 24 guests at a stirred bar service. Use the recipe in the examples folder.

Expected: agent loads `old-fashioned.json`, runs the script with `--servings 24`, surfaces the batch card. Final ABV ~32%, moderation warning fires.

### 2. Edge case

> Scale the Margarita example to 50 guests, shaken, and target 14% ABV in the final glass. Output in ounces.

Expected: agent runs with `--servings 50 --target-abv 14 --units oz`. Script reports `above_target` (final 18.3%) and recommends a method with more dilution or a lower spirit ratio. Agent surfaces this honestly rather than pretending the target was hit.

### 3. Cautious / partial-decline case

> Pre-batch the Aperol Spritz example for 12 people but bring it up to 18% ABV — I want it to hit harder.

Expected: script returns exit code 3, `infeasible_above_max`. Agent does **not** silently relax the target. It surfaces the physics — pre-dilution ABV ceiling is 12.8%, target 18% is unreachable by dilution alone — and offers concrete adjustments (raise the spirit content, swap modifier, lower target). The skill's `SKILL.md` also flags any framing whose explicit goal is rapid intoxication; the model should redirect the user to lower-ABV alternatives or food/water pacing.

## What worked well

- **Clean orchestration boundary.** The script does only deterministic work and refuses to make judgment calls (e.g., it surfaces infeasibility rather than auto-relaxing the target). Everything qualitative — flavor, garnish, glass, moderation phrasing — is left to the model.
- **Dependency-free.** Pure Python stdlib. Reproducible on any machine with Python 3.9+.
- **JSON input plus CLI overrides** keeps the recipe authoring path simple while letting the agent layer in `--servings`, `--method`, and `--target-abv` from conversation context.
- **Structured exit codes** make it easy for the agent to branch on outcomes (success / validation failure / infeasibility) rather than parsing prose.

## Limitations

- The dilution model is a planning approximation, not a measurement. Real dilution depends on ice geometry, technique time, and ambient temperature. For competition or commercial work, measure with a refractometer.
- ABV inputs are trusted. If the user (or the model's inference) is wrong about an ingredient's ABV, the math is right but the answer is wrong. The skill instructs the model to surface its inferred ABVs to the user for confirmation.
- Volumetric contraction (alcohol + water mix to slightly less than the sum of parts) is ignored. The error is well below pour precision.
- The `none` method assumes pre-batched bottling with no ice contact yet; the user must dilute at service. The skill surfaces this assumption explicitly.

## License

See `LICENSE`.
