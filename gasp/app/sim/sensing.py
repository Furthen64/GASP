from gasp.app.sim.constants import CellType, Facing
from gasp.app.util.math_helpers import neighbor_ring, rect_cells

def neighbor_ring_cells(creature, world):
    """Return list of (x, y, CellType) for cells adjacent to creature."""
    ring = neighbor_ring(creature.x, creature.y, creature.width, creature.height)
    result = []
    for cx, cy in ring:
        ct = world.get_cell_type(cx, cy)
        result.append((cx, cy, ct))
    return result

def _front_cell(creature, world):
    """Get cell(s) directly in front of creature (based on facing)."""
    cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
    front = set()
    if creature.facing == Facing.N:
        for cx, cy in cells:
            front.add((cx, cy - 1))
    elif creature.facing == Facing.S:
        for cx, cy in cells:
            front.add((cx, cy + 1))
    elif creature.facing == Facing.E:
        for cx, cy in cells:
            front.add((cx + 1, cy))
    elif creature.facing == Facing.W:
        for cx, cy in cells:
            front.add((cx - 1, cy))
    return front - cells

def compute_sensed(creature, world) -> dict:
    ring = neighbor_ring_cells(creature, world)
    food_count = sum(1 for _, _, ct in ring if ct == CellType.FOOD)
    toxic_count = sum(1 for _, _, ct in ring if ct == CellType.TOXIC)
    wall_count = sum(1 for _, _, ct in ring if ct in (CellType.WALL, CellType.BORDER))
    free_count = sum(1 for _, _, ct in ring if ct == CellType.GROUND)

    # Partner count: other creatures adjacent
    occupied = world.cells_occupied_by_creatures()
    my_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
    ring_coords = {(cx, cy) for cx, cy, _ in ring}
    partner_cells = ring_coords & occupied
    # Find distinct creatures
    partner_ids = set()
    for cx, cy in partner_cells:
        c = world.get_creature_at(cx, cy)
        if c and c.id != creature.id:
            partner_ids.add(c.id)
    partner_count = len(partner_ids)

    # Can grow: check if any adjacent cell is free ground (within bounds, not occupied, not wall)
    can_grow = int(any(
        ct == CellType.GROUND and world.is_cell_movable_to(cx, cy)
        for cx, cy, ct in ring
    ))

    # Can move forward
    front = _front_cell(creature, world)
    can_move = int(all(
        world.is_cell_movable_to(cx, cy)
        for cx, cy in front
    ) and len(front) > 0)

    # Can reproduce
    params = world.params
    can_reproduce = int(
        creature.energy >= params.reproduction_cost * 1.5 and
        find_adjacent_free_spot(creature, world) is not None
    )

    return {
        'food_count': food_count,
        'toxic_count': toxic_count,
        'wall_count': wall_count,
        'free_count': free_count,
        'partner_count': partner_count,
        'can_grow': can_grow,
        'can_move_forward': can_move,
        'can_reproduce': can_reproduce,
    }

def find_adjacent_free_spot(creature, world):
    """Find an adjacent free cell for a new child."""
    ring = neighbor_ring(creature.x, creature.y, creature.width, creature.height)
    for cx, cy in ring:
        if world.is_cell_movable_to(cx, cy):
            return (cx, cy)
    return None
