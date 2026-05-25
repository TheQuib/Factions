# Sprites

Drop PNG files here to override the procedural pixel-art drawing.

## Naming

| File name             | Replaces                            |
|-----------------------|-------------------------------------|
| `hive_swarm.png`      | Hive Swarm unit                     |
| `hive_soldier.png`    | Hive Soldier unit                   |
| `pal_knight.png`      | Paladin Knight unit                 |
| `elem_fire.png`       | Fire Titan                          |
| `bldg_castle.png`     | All castles (tinted per faction)    |
| `bldg_tower.png`      | Arrow towers                        |
| `bldg_farm.png`       | Farm building                       |
| *(etc.)*              | Any unit type or `bldg_<btype>`     |

## Sizes (recommended)

| Target       | Source PNG size | Canvas draw size |
|--------------|-----------------|-----------------|
| Units        | 32 × 32 px      | 64 × 64 px (2×) |
| Buildings    | 32 × 32 px      | 64 × 64 px (2×) |
| Castles      | 64 × 64 px      | 128 × 128 px (2×) |
| Titans       | 64 × 64 px      | 128 × 128 px (2×) |

Sprites are rendered at 2× their source size for crisp pixel art scaling.
Image smoothing is disabled on the canvas, so sprites stay sharp.
Keep backgrounds transparent (RGBA PNG). The flash highlight and HP bar
are drawn on top by the engine.

## Fallback

Any file that is missing silently falls back to the original procedural
`fillRect` pixel art. You can add sprites one at a time.
