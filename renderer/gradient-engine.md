# Coffee Visual Identity Engine 2.1

## Processing pipeline

1. Detect one dominant processing method from `--processing-method` or the coffee name. Prefer the first exact alias in `detection_order`; this makes carbonic maceration and anaerobic override generic natural wording.
2. Resolve every flavor from the unchanged 180-item `references/flavor-colors.json` table. Flavor answers “what hue is this?”.
3. Apply the processing personality from `assets/processing-color-system.json`. Processing answers “how should this hue appear?” through palette undertone, chroma, temperature, contrast, diffusion, field warp, and texture.
4. Select at most one main motif and one complementary auxiliary motif from `assets/flavor-motif-system.json`.
5. Render the transformed flavor palette as multiple organic fields and blend the oversized, cropped motif fields into it.
6. Detect origin from `--origin` or the coffee name and retain its small adjustment.
7. Apply the processing texture pass after the motif layer.

Conceptual priority is Processing 60% / Flavor 30% / Origin 10%. Do not interpret it as a flat RGB average. Processing dominates the visual grammar, flavor remains the hue source, and origin stays a restrained accent.

## Motif selection and rendering

- Choose the earliest supported flavor as `main`.
- For `auxiliary`, prefer the earliest later flavor whose shape is listed in the main motif's `preferred_auxiliary_shapes`; otherwise choose the earliest different visual family.
- Render no more than two motifs. Unsupported flavors still contribute color.
- Build motifs procedurally as soft scalar fields: radial petals, organic pulp, seed burst, cluster blobs, translucent rings, mist ribbon, viscous flow, or liquid bloom.
- Place main and auxiliary motifs on opposite edges, crop them at the canvas boundary, blur them, and blend them in OKLab using their flavor colors.
- Never render literal fruit, flowers, food, complete objects, icons, stickers, cartoons, or hard outlines.

## Texture mapping

- Washed → glass diffusion: broad translucent fields, low chroma/contrast, light grain.
- Natural → sun grain: warm diffusion, medium-high chroma, tactile sunlit grain.
- Honey → liquid glow: smooth fields, amber undertone, soft local glow.
- Anaerobic → spray particle: saturated high-contrast fields, irregular warp, sparse colored particles.
- Carbonic maceration → precision micrograin: cooler premium palette, controlled diffusion, fine grain.
- Unknown → neutral matte grain. Preserve backward compatibility and mark detection as fallback in metadata.

## Invariant

Never encode flavor-to-color mappings in the processing system. Peach remains peach in the flavor table; processing only changes whether peach appears transparent and pale, warm and sweet, or fluorescent and high-contrast.

Motifs encode only abstract shape metaphors. A Jasmine motif is a blurred radial petal field, not a jasmine illustration; a Passion Fruit motif is an organic seed burst, not a sliced fruit.
