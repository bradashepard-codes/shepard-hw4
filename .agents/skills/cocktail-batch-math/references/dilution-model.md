# Dilution model — sourcing and assumptions

The script's `DILUTION_FACTORS` table approximates the volume gain a cocktail experiences from ice melt during preparation. Values are widely used planning approximations, not lab measurements.

## Values used

| Method   | Volume gain | Rationale |
|----------|-------------|-----------|
| stirred  | +25%        | Standard agitation over ice for ~30s. Spirit-forward drinks (Old Fashioned, Manhattan, Martini) target this range. |
| shaken   | +50%        | Vigorous agitation with ice for ~10-15s. Citrus / dairy / egg-white drinks need the aeration and dilution. |
| built    | +15%        | Built directly in the serving glass over ice; minimal active mixing. Highballs, Mojitos pre-bubble. |
| blended  | +75%        | Crushed ice + blade; dilution is significant and depends heavily on ice ratio. |
| none     | 0%          | Bottled / pre-batched, no ice contact yet. Final ABV equals pre-dilution ABV; the user dilutes at service. |

## Source

Primary reference: Dave Arnold, *Liquid Intelligence: The Art and Science of the Perfect Cocktail* (W. W. Norton, 2014). Arnold's measurements of stirred and shaken dilution at standard ice and timing landed in the 20-25% (stirred) and 45-55% (shaken) ranges; the values used here are conservative midpoints widely echoed in industry training materials (Death & Co's *Cocktail Codex*, the BarSmarts curriculum, and similar).

## What the model does NOT account for

- **Ice quality.** Hand-cut large-format ice dilutes less per unit time than small machine cubes. The model uses generic timings.
- **Technique time.** A 60-second stir dilutes more than a 20-second stir.
- **Ambient temperature.** Hot bar = faster melt = more dilution.
- **Volumetric contraction.** Alcohol + water mixtures occupy slightly less volume than the sum of their parts (~0.5% at typical cocktail strengths). The script ignores this; the error is well below pour precision.
- **Pre-batching at scale.** Bottled batches with delayed ice contact behave differently from one-off drinks; treat the `none` method as the right starting point for those, then add expected service dilution separately.

## When to override

For competition prep, commercial menu development, or any context where the final ABV must be measurably correct, do not rely on this model — measure directly with a refractometer or hydrometer. The model is intended for planning home and small-event batches where ±2% post-dilution ABV is acceptable.
