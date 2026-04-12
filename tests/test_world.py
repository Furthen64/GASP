import pytest
from gasp.app.persistence.params_io import Parameters, SEED_MODE_FIXED, SEED_MODE_RANDOM
from gasp.app.sim.world import World
from gasp.app.sim.constants import CellType

@pytest.fixture
def default_world():
    from gasp.app.util.ids import CREATURE_ID_GEN
    CREATURE_ID_GEN.reset(0)
    params = Parameters()
    world = World(params)
    world.initialize_default()
    return world

def test_border_walls(default_world):
    w = default_world
    # Check top and bottom rows
    for x in range(w.width):
        assert w.get_cell_type(x, 0) == CellType.BORDER, f"Top border missing at ({x}, 0)"
        assert w.get_cell_type(x, w.height - 1) == CellType.BORDER, f"Bottom border missing"
    # Check left and right columns
    for y in range(w.height):
        assert w.get_cell_type(0, y) == CellType.BORDER, f"Left border missing at (0, {y})"
        assert w.get_cell_type(w.width - 1, y) == CellType.BORDER, f"Right border missing"

def test_initial_creature_count(default_world):
    living = [c for c in default_world.creatures.values() if c.alive]
    assert len(living) == 4, f"Expected 4 initial creatures, got {len(living)}"

def test_step_increments(default_world):
    w = default_world
    assert w.step == 0
    w.step_world()
    assert w.step == 1
    w.step_world()
    assert w.step == 2

def test_food_no_overlap_walls(default_world):
    w = default_world
    for cell in w.food_cells:
        ct = w.terrain.get(cell)
        assert ct not in (CellType.WALL, CellType.BORDER), \
            f"Food at wall/border cell {cell}"
        x, y = cell
        assert 0 < x < w.width - 1 and 0 < y < w.height - 1, \
            f"Food on border at {cell}"

def test_spatial_index_matches_creature_cells(default_world):
    w = default_world
    occupied = w.cells_occupied_by_creatures()
    assert occupied
    for cell in occupied:
        creature = w.get_creature_at(*cell)
        assert creature is not None
        assert creature.alive

def test_step_records_timing_profile(default_world):
    w = default_world
    w.step_world()

    assert w.last_step_profile.total_ms >= 0.0
    assert 'creature_sense' in w.last_step_profile.phase_ms
    assert 'creature_action' in w.last_step_profile.phase_ms
    assert w.step_timings.latest is w.last_step_profile

def test_initial_creatures_respect_max_creatures():
    from gasp.app.persistence.params_io import Parameters
    from gasp.app.util.ids import CREATURE_ID_GEN

    CREATURE_ID_GEN.reset(0)
    params = Parameters(initial_creature_count=10, max_creatures=3)
    world = World(params)
    world.initialize_default()

    assert world.living_creature_count() == 3

def test_world_uses_params_seed_when_not_overridden():
    params = Parameters(seed=123456, seed_mode=SEED_MODE_FIXED)
    world_a = World(params)
    world_b = World(params)

    assert world_a.rng.random() == world_b.rng.random()

def test_random_seed_mode_generates_new_seed_values():
    params = Parameters(seed=42, seed_mode=SEED_MODE_RANDOM)

    first = params.resolve_seed()
    second = params.resolve_seed()

    assert 0 <= first <= 2_147_483_647
    assert 0 <= second <= 2_147_483_647
    assert first != second
