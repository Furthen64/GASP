import pytest
from gasp.app.persistence.params_io import Parameters, SEED_MODE_FIXED, SEED_MODE_RANDOM
from gasp.app.sim.actions import do_move, move_energy_cost
from gasp.app.sim.fitness import compute_fitness
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
    assert params.move_energy_area_scale == 0.35
    assert params.epoch_fitness_reproduction_weight == 8.0

def test_move_energy_cost_scales_with_area():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=0,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        move_energy_base_cost=0.25,
        move_energy_area_scale=0.5,
    )
    world = World(params)
    world.initialize_default()

    small = Creature(id=1, x=2, y=2, facing=Facing.E, energy=100.0)
    large = Creature(id=2, x=2, y=4, width=2, height=2, facing=Facing.E, energy=100.0)
    world.creatures = {small.id: small, large.id: large}
    world.invalidate_spatial_index()

    expected_small_cost = move_energy_cost(small, params)
    expected_large_cost = move_energy_cost(large, params)

    assert expected_large_cost > expected_small_cost
    assert do_move(small, world) is True
    assert do_move(large, world) is True
    assert small.energy == pytest.approx(100.0 - expected_small_cost)
    assert large.energy == pytest.approx(100.0 - expected_large_cost)
    assert large.move_energy_spent == pytest.approx(expected_large_cost)

def test_epoch_fitness_rewards_mixed_outcomes():
    params = Parameters(initial_energy=100.0)
    explorer = Creature(
        id=1,
        lifetime_ticks=20,
        distance_traveled=36.0,
        energy=80.0,
        move_energy_spent=4.0,
    )
    reproducer = Creature(
        id=2,
        lifetime_ticks=12,
        distance_traveled=6.0,
        energy=55.0,
        pregnancies_completed=2,
        food_eaten=2,
        move_energy_spent=1.5,
    )
    poisoned = Creature(
        id=3,
        lifetime_ticks=25,
        distance_traveled=30.0,
        energy=35.0,
        toxic_ticks=6,
        move_energy_spent=8.0,
    )

    assert compute_fitness(reproducer, params) > compute_fitness(explorer, params)
    assert compute_fitness(explorer, params) > compute_fitness(poisoned, params)

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
        lifetime_ticks=18,
        distance_traveled=10.0,
        pregnancies_completed=2,
        food_eaten=3,
        energy=60.0,
        move_energy_spent=2.0,
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
        lifetime_ticks=35,
        distance_traveled=20.0,
        food_eaten=1,
        energy=20.0,
        move_energy_spent=9.0,
        toxic_ticks=3,
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
    assert next_world.last_epoch_summary['best_pregnancies'] == 2
    assert next_world.last_epoch_summary['best_food_eaten'] == 3
    assert next_world.last_epoch_summary['best_fitness_breakdown']['reproduction'] > 0.0
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
