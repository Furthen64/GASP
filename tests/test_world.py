import pytest
from gasp.app.persistence.params_io import Parameters, SEED_MODE_FIXED, SEED_MODE_RANDOM
from gasp.app.sim.world import World
from gasp.app.sim.constants import CellType, ActionType, Facing, SignalId, CompareOp
from gasp.app.sim.creature import Creature
from gasp.app.sim.genetics import Promoter, Unit

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
    assert len(living) == 8, f"Expected 8 initial creatures, got {len(living)}"

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

def test_default_parameters_favor_small_randomized_runs():
    params = Parameters()

    assert params.world_width == 64
    assert params.world_height == 42
    assert params.initial_creature_count == 8
    assert params.max_creatures == 10
    assert params.seed_mode == SEED_MODE_RANDOM
    assert params.food_spawn_rate == 0.002
    assert params.initial_food_count == 40
    assert params.energy_per_food == 50.0

def test_build_next_epoch_world_carries_best_creatures():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=2,
        max_creatures=2,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        seed=123,
        seed_mode=SEED_MODE_FIXED,
    )
    world = World(params)
    world.initialize_default(seed_creatures=[])
    world.creatures = {}

    best = Creature(
        id=10,
        generation=2,
        x=2,
        y=2,
        lifetime_ticks=30,
        distance_traveled=12.0,
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=2.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            )
        ],
    )
    runner_up = Creature(
        id=11,
        generation=1,
        x=3,
        y=3,
        lifetime_ticks=12,
        distance_traveled=1.0,
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.TURN_RIGHT,
            )
        ],
    )
    world.creatures = {best.id: best, runner_up.id: runner_up}
    next_world = world.build_next_epoch_world()

    assert next_world.epoch == 2
    assert next_world.last_epoch_summary is not None
    assert next_world.last_epoch_summary['epoch'] == 1
    assert next_world.last_epoch_summary['best_creature_id'] == best.id
    assert next_world.last_epoch_summary['elite_ids'] == [best.id, runner_up.id]
    assert next_world.seed != world.seed
    assert next_world.living_creature_count() == 2

    offspring = sorted(next_world.creatures.values(), key=lambda creature: creature.parent_ids[0])
    assert [creature.parent_ids[0] for creature in offspring] == [best.id, runner_up.id]
    assert offspring[0].generation == best.generation + 1
    assert offspring[0].chromosome[0].gene == best.chromosome[0].gene

def test_blocked_move_falls_back_to_feasible_action():
    params = Parameters(
        world_width=6,
        world_height=6,
        initial_creature_count=0,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=1,
        y=1,
        facing=Facing.N,
        energy=100.0,
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=2.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.TURN_RIGHT,
            ),
        ],
    )
    world.creatures[creature.id] = creature
    world.invalidate_spatial_index()

    world.step_world()

    assert creature.last_action == ActionType.TURN_RIGHT
    assert creature.facing == Facing.E
    assert (creature.x, creature.y) == (1, 1)
