def rect_cells(x, y, w, h):
    """Return set of all (cx,cy) tuples within rect."""
    return {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}

def neighbor_ring(x, y, w, h):
    """Return set of (cx,cy) outside the rect but directly adjacent (8-connected border ring)."""
    interior = rect_cells(x, y, w, h)
    candidates = set()
    for cx, cy in interior:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                candidates.add((cx + dx, cy + dy))
    return candidates - interior

def rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
    """Return True if two rectangles overlap."""
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)

def rect_in_bounds(x, y, w, h, world_w, world_h):
    """Return True if rect is fully within world bounds."""
    return x >= 0 and y >= 0 and x + w <= world_w and y + h <= world_h
