"""
SpatialGrid — fast O(1)-insert, O(local) neighbour queries.

The map is divided into fixed-size cells.  Each entity registers itself
in the cell(s) it overlaps.  Neighbour queries only visit the cells
within radius r, so the hot "find nearest enemy" loops shrink from
O(n) to O(k) where k is the local crowd density.

Usage (inside Simulation.tick):

    sim.grid.clear()
    for e in sim.entities:
        sim.grid.insert(e)

Then in Unit / Building targeting:

    candidates = sim.grid.query(self.x, self.y, self.rng + 10)
    # candidates is a list of entities in the neighbourhood
"""

import math
from typing import List

# Cell size in world-pixels.  Larger = fewer cells but more entities per query.
# 120 px ≈ the attack range of most ranged units, so one-ring look-up covers them.
CELL = 120


class SpatialGrid:
    def __init__(self, map_w: int, map_h: int, cell: int = CELL):
        self.cell   = cell
        self.cols   = math.ceil(map_w / cell) + 1
        self.rows   = math.ceil(map_h / cell) + 1
        # Flat dict: (col, row) -> list[entity]
        self._cells: dict = {}

    # ── Mutation ──────────────────────────────────────────────────────────────

    def clear(self):
        self._cells.clear()

    def insert(self, entity):
        c = int(entity.x / self.cell)
        r = int(entity.y / self.cell)
        key = (c, r)
        bucket = self._cells.get(key)
        if bucket is None:
            self._cells[key] = [entity]
        else:
            bucket.append(entity)

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(self, x: float, y: float, radius: float) -> List:
        """Return all entities whose cell overlaps a circle of *radius* around (x,y).

        The result may include entities slightly outside the radius; callers
        should do a precise distance check when needed.  The list is a fresh
        list so callers may filter it in place.
        """
        span   = int(radius / self.cell) + 1
        c0     = int(x / self.cell)
        r0     = int(y / self.cell)
        result = []
        get    = self._cells.get
        for dc in range(-span, span + 1):
            for dr in range(-span, span + 1):
                bucket = get((c0 + dc, r0 + dr))
                if bucket:
                    result.extend(bucket)
        return result

    def query_rect(self, x: float, y: float, w: float, h: float) -> List:
        """Return entities whose cell overlaps the rectangle [x, x+w] × [y, y+h]."""
        c0 = int(x / self.cell)
        c1 = int((x + w) / self.cell)
        r0 = int(y / self.cell)
        r1 = int((y + h) / self.cell)
        result = []
        get = self._cells.get
        for c in range(c0, c1 + 1):
            for r in range(r0, r1 + 1):
                bucket = get((c, r))
                if bucket:
                    result.extend(bucket)
        return result