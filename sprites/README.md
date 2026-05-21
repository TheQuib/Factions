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

| Target       | Canvas draw size |
|--------------|-----------------|
| Units        | 32 × 32 px       |
| Buildings    | 32 × 32 px       |
| Castles      | 64 × 64 px       |
| Titans       | 64 × 64 px       |

Larger source images are fine — they'll be scaled down. Keep backgrounds
transparent (RGBA PNG). The flash highlight and HP bar are drawn on top by
the engine.

## Fallback

Any file that is missing silently falls back to the original procedural
`fillRect` pixel art. You can add sprites one at a time.
