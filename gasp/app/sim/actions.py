from gasp.app.sim.constants import ActionType, Facing, CellType, MAX_CREATURE_SIZE
from gasp.app.util.math_helpers import rect_cells, rect_in_bounds

def _delta_for_facing(facing: Facing):
    return {
        Facing.N: (0, -1),
        Facing.S: (0, 1),
        Facing.E: (1, 0),
        Facing.W: (-1, 0),
    }[facing]

def do_move(creature, world) -> bool:
    dx, dy = _delta_for_facing(creature.facing)
    nx, ny = creature.x + dx, creature.y + dy
    # Check all new cells are free and in bounds
    new_cells = rect_cells(nx, ny, creature.width, creature.height)
    old_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
    cells_to_check = new_cells - old_cells
    if not rect_in_bounds(nx, ny, creature.width, creature.height,
                          world.width, world.height):
        return False
    for cx, cy in cells_to_check:
        if not world.is_cell_movable_to(cx, cy):
            return False
    old_x, old_y = creature.x, creature.y
    creature.x = nx
    creature.y = ny
    world.invalidate_spatial_index()
    dist = (dx ** 2 + dy ** 2) ** 0.5
    creature.distance_traveled += dist
    return True

def do_turn_left(creature, world) -> bool:
    order = [Facing.N, Facing.W, Facing.S, Facing.E]
    idx = order.index(creature.facing)
    creature.facing = order[(idx + 1) % 4]
    return True

def do_turn_right(creature, world) -> bool:
    order = [Facing.N, Facing.E, Facing.S, Facing.W]
    idx = order.index(creature.facing)
    creature.facing = order[(idx + 1) % 4]
    return True

def do_eat(creature, world) -> bool:
    my_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
    # Eat from adjacent food cells
    from gasp.app.util.math_helpers import neighbor_ring
    ring = neighbor_ring(creature.x, creature.y, creature.width, creature.height)
    food_found = ring & world.food_cells
    if not food_found:
        # Also check under creature
        food_under = my_cells & world.food_cells
        if food_under:
            cell = next(iter(food_under))
            world.food_cells.discard(cell)
            creature.energy += world.params.energy_per_food
            return True
        return False
    cell = next(iter(food_found))
    world.food_cells.discard(cell)
    creature.energy += world.params.energy_per_food
    return True

def do_grow(creature, world, direction: Facing) -> bool:
    dx, dy = _delta_for_facing(direction)
    # Try expanding in given direction
    if direction == Facing.N:
        new_y = creature.y - 1
        new_cells = {(cx, new_y) for cx in range(creature.x, creature.x + creature.width)}
        if creature.height >= MAX_CREATURE_SIZE:
            return False
        if any(not world.is_cell_movable_to(cx, cy) for cx, cy in new_cells):
            return False
        if not rect_in_bounds(creature.x, new_y, creature.width, creature.height + 1,
                              world.width, world.height):
            return False
        creature.y = new_y
        creature.height += 1
        world.invalidate_spatial_index()
        return True
    elif direction == Facing.S:
        new_y = creature.y + creature.height
        new_cells = {(cx, new_y) for cx in range(creature.x, creature.x + creature.width)}
        if creature.height >= MAX_CREATURE_SIZE:
            return False
        if any(not world.is_cell_movable_to(cx, cy) for cx, cy in new_cells):
            return False
        if not rect_in_bounds(creature.x, creature.y, creature.width, creature.height + 1,
                              world.width, world.height):
            return False
        creature.height += 1
        world.invalidate_spatial_index()
        return True
    elif direction == Facing.E:
        new_x = creature.x + creature.width
        new_cells = {(new_x, cy) for cy in range(creature.y, creature.y + creature.height)}
        if creature.width >= MAX_CREATURE_SIZE:
            return False
        if any(not world.is_cell_movable_to(cx, cy) for cx, cy in new_cells):
            return False
        if not rect_in_bounds(creature.x, creature.y, creature.width + 1, creature.height,
                              world.width, world.height):
            return False
        creature.width += 1
        world.invalidate_spatial_index()
        return True
    elif direction == Facing.W:
        new_x = creature.x - 1
        new_cells = {(new_x, cy) for cy in range(creature.y, creature.y + creature.height)}
        if creature.width >= MAX_CREATURE_SIZE:
            return False
        if any(not world.is_cell_movable_to(cx, cy) for cx, cy in new_cells):
            return False
        if not rect_in_bounds(new_x, creature.y, creature.width + 1, creature.height,
                              world.width, world.height):
            return False
        creature.x = new_x
        creature.width += 1
        world.invalidate_spatial_index()
        return True
    return False

def do_reproduce(creature, world) -> bool:
    if creature.energy < world.params.reproduction_cost:
        return False
    if not world.can_queue_birth():
        return False
    pregnancy_chance = min(1.0, max(0.0, world.params.pregnancy_chance))
    if world.rng.random() >= pregnancy_chance:
        return False
    creature.energy -= world.params.reproduction_cost
    world.pending_births.append(creature.id)
    return True

def do_idle(creature, world) -> bool:
    return True

def do_analyze(creature, world) -> bool:
    # Refresh sensed values (already done each tick, but can be explicit)
    from gasp.app.sim.sensing import compute_sensed
    creature.sensed = compute_sensed(creature, world)
    return True

def execute_action(action_type: ActionType, creature, world) -> bool:
    if action_type == ActionType.MOVE:
        return do_move(creature, world)
    elif action_type == ActionType.TURN_LEFT:
        return do_turn_left(creature, world)
    elif action_type == ActionType.TURN_RIGHT:
        return do_turn_right(creature, world)
    elif action_type == ActionType.EAT:
        return do_eat(creature, world)
    elif action_type == ActionType.GROW_N:
        return do_grow(creature, world, Facing.N)
    elif action_type == ActionType.GROW_E:
        return do_grow(creature, world, Facing.E)
    elif action_type == ActionType.GROW_S:
        return do_grow(creature, world, Facing.S)
    elif action_type == ActionType.GROW_W:
        return do_grow(creature, world, Facing.W)
    elif action_type == ActionType.REPRODUCE:
        return do_reproduce(creature, world)
    elif action_type == ActionType.IDLE:
        return do_idle(creature, world)
    elif action_type == ActionType.ANALYZE:
        return do_analyze(creature, world)
    return False
