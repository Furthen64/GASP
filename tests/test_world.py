import pytest
from gasp.app.persistence.params_io import Parameters, SEED_MODE_FIXED, SEED_MODE_RANDOM
from gasp.app.sim.actions import do_move, move_energy_cost
from gasp.app.sim.fitness import compute_fitness, compute_fitness_breakdown
from gasp.app.sim.sensing import compute_sensed
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

def test_step_records_epoch_score_history(default_world):
    w = default_world
    creature = next(iter(w.creatures.values()))

    assert creature.fitness_history == []

    w.step_world()

    assert len(creature.fitness_history) == 1
    assert isinstance(creature.fitness_history[0], float)

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

def test_default_parameters_favor_sparse_epoch_runs():
    params = Parameters()

    assert params.world_width == 70
    assert params.world_height == 64
    assert params.initial_creature_count == 8
    assert params.max_creatures == 25
    assert params.seed_mode == SEED_MODE_RANDOM
    assert params.food_spawn_rate == 0.0001
    assert params.initial_food_count == 102
    assert params.initial_creature_spawn_min_distance == 8
    assert params.internal_state_count == 4
    assert params.energy_per_food == 50.0
    assert params.move_energy_area_scale == 0.35
    assert params.epoch_fitness_reproduction_weight == 8.0
    assert params.epoch_fitness_survival_weight == 0.0
    assert params.epoch_fitness_exploration_weight == 1.0
    assert params.epoch_fitness_food_weight == 25.0
    assert params.epoch_fitness_program_complexity_weight == 0.75
    assert params.epoch_fitness_behavior_diversity_weight == 1.0
    assert params.epoch_fitness_move_penalty == 0.0
    assert params.epoch_fitness_idle_penalty == 4.0
    assert params.runtime_learning_rate == 0.4
    assert params.runtime_learning_decay == 0.92
    assert params.runtime_reward_food == 5.0
    assert params.runtime_penalty_failed_action == 1.4
    assert params.runtime_penalty_blocked_idle == 1.2

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

def test_moving_over_food_grants_immediate_epoch_fitness():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
        move_energy_base_cost=0.0,
        move_energy_area_scale=0.0,
        initial_energy=100.0,
        epoch_fitness_food_weight=25.0,
    )
    world = World(params)
    world.initialize_default()

    mover = Creature(
        id=1,
        x=2,
        y=2,
        facing=Facing.E,
        energy=100.0,
        visited_positions=[(2, 2)],
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            )
        ],
    )
    world.creatures = {mover.id: mover}
    world.food_cells = {(3, 2)}
    world.invalidate_spatial_index()

    before = compute_fitness(mover, params)
    before_breakdown = compute_fitness_breakdown(mover, params)
    assert mover.fitness_history == []

    world.step_world()

    assert (mover.x, mover.y) == (3, 2)
    assert mover.food_eaten == 1
    assert (3, 2) not in world.food_cells
    after = compute_fitness(mover, params)
    after_breakdown = compute_fitness_breakdown(mover, params)

    assert after_breakdown['food'] == pytest.approx(
        before_breakdown['food'] + params.epoch_fitness_food_weight
    )
    assert after >= before + params.epoch_fitness_food_weight
    assert mover.fitness_history[-1] == pytest.approx(after)
    assert mover.last_reward > 0.0
    assert mover.learned_biases[0] > 0.0

def test_runtime_learning_penalizes_idle_rule_and_switches_action():
    params = Parameters(
        world_width=5,
        world_height=5,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
        runtime_learning_rate=0.8,
        runtime_learning_decay=1.0,
        runtime_penalty_failed_action=1.5,
        runtime_reward_action_success=0.2,
        runtime_penalty_idle=0.8,
        runtime_penalty_blocked_idle=1.2,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=3,
        y=2,
        facing=Facing.E,
        energy=100.0,
        visited_positions=[(3, 2)],
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.IDLE,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=0.9,
                ),
                target_type='gene',
                gene=ActionType.TURN_LEFT,
            ),
        ],
    )
    world.creatures = {creature.id: creature}
    world.invalidate_spatial_index()

    world.step_world()
    assert creature.last_action == ActionType.IDLE
    assert creature.last_action_success is True
    assert creature.blocked_forward_ticks == 1
    assert creature.learned_biases[0] < 0.0
    assert creature.reward_history[-1] < -1.0

    world.step_world()
    assert creature.last_action == ActionType.TURN_LEFT
    assert creature.last_action_success is True
    assert creature.blocked_forward_ticks == 0
    assert creature.learned_biases[1] > 0.0

def test_runtime_learning_rewards_food_without_erasing_it_on_next_bad_tick():
    params = Parameters(
        world_width=5,
        world_height=5,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
        move_energy_base_cost=0.0,
        move_energy_area_scale=0.0,
        runtime_learning_rate=0.5,
        runtime_learning_decay=0.95,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=2,
        y=2,
        facing=Facing.E,
        energy=100.0,
        visited_positions=[(2, 2)],
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            )
        ],
    )
    world.creatures = {creature.id: creature}
    world.food_cells = {(3, 2)}
    world.invalidate_spatial_index()

    world.step_world()
    positive_trace = creature.reward_trace
    positive_bias = creature.learned_biases[0]
    assert positive_trace > 0.0
    assert positive_bias > 0.0
    assert creature.reward_history[-1] > 0.0

    world.step_world()
    assert creature.last_action == ActionType.IDLE
    assert creature.last_action_success is True
    assert creature.learned_biases[0] < positive_bias
    assert creature.reward_trace < positive_trace
    assert creature.reward_trace > 0.0

def test_epoch_fitness_rewards_mixed_outcomes():
    params = Parameters(initial_energy=100.0)
    explorer = Creature(
        id=1,
        lifetime_ticks=20,
        distance_traveled=36.0,
        energy=80.0,
        move_energy_spent=4.0,
        visited_positions=[(1, 1), (2, 1), (3, 1), (4, 1), (4, 2), (5, 2), (6, 2)],
    )
    reproducer = Creature(
        id=2,
        lifetime_ticks=12,
        distance_traveled=6.0,
        energy=55.0,
        pregnancies_completed=2,
        food_eaten=2,
        move_energy_spent=1.5,
        visited_positions=[(1, 1), (2, 1), (2, 2)],
    )
    poisoned = Creature(
        id=3,
        lifetime_ticks=25,
        distance_traveled=30.0,
        energy=35.0,
        toxic_ticks=6,
        move_energy_spent=8.0,
        visited_positions=[(1, 1), (2, 1), (3, 1), (2, 1), (3, 1)],
    )

    assert compute_fitness(reproducer, params) > compute_fitness(explorer, params)
    assert compute_fitness(explorer, params) > compute_fitness(poisoned, params)

def test_epoch_fitness_prefers_exploration_over_turning_in_place():
    params = Parameters(initial_energy=100.0)
    turning = Creature(
        id=1,
        lifetime_ticks=40,
        energy=82.0,
        visited_positions=[(2, 2)],
    )
    explorer = Creature(
        id=2,
        lifetime_ticks=26,
        energy=58.0,
        move_energy_spent=5.5,
        visited_positions=[(2, 2), (3, 2), (4, 2), (5, 2), (5, 3), (6, 3), (6, 4), (7, 4)],
    )

    assert compute_fitness(explorer, params) > compute_fitness(turning, params)

def test_epoch_fitness_penalizes_idle_heavily():
    params = Parameters(initial_energy=100.0)
    idler = Creature(
        id=1,
        lifetime_ticks=30,
        energy=90.0,
        idle_ticks=12,
        actions_seen=['IDLE'],
        states_seen=[0],
        visited_positions=[(2, 2)],
    )
    explorer = Creature(
        id=2,
        lifetime_ticks=18,
        energy=55.0,
        distance_traveled=20.0,
        food_eaten=1,
        actions_seen=['MOVE', 'TURN_RIGHT', 'EAT'],
        states_seen=[0, 1, 2],
        visited_positions=[(2, 2), (3, 2), (4, 2), (4, 3), (5, 3)],
    )

    assert compute_fitness(explorer, params) > compute_fitness(idler, params)

def test_initial_creatures_spawn_with_dispersion():
    params = Parameters(
        world_width=30,
        world_height=30,
        initial_creature_count=8,
        max_creatures=8,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        initial_creature_spawn_min_distance=8,
        seed=13,
        seed_mode=SEED_MODE_FIXED,
    )
    world = World(params)
    world.initialize_default()

    positions = [(creature.x, creature.y) for creature in world.creatures.values() if creature.alive]
    assert len(positions) == 8
    for index, cell in enumerate(positions):
        others = positions[:index] + positions[index + 1:]
        if others:
            assert world._distance_to_nearest(cell, others) >= 8

def test_compute_sensed_reports_directional_food_and_space():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=0,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(id=1, x=3, y=3, facing=Facing.N, energy=100.0, visited_positions=[(3, 3)])
    world.creatures = {creature.id: creature}
    world.food_cells = {(3, 2), (2, 3), (4, 3)}
    world.invalidate_spatial_index()

    sensed = compute_sensed(creature, world)

    assert sensed['food_ahead'] == 1
    assert sensed['food_left'] == 1
    assert sensed['food_right'] == 1
    assert sensed['free_ahead'] == 0
    assert sensed['can_eat'] == 1

def test_step_turns_toward_directional_food():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=3,
        y=3,
        facing=Facing.N,
        energy=100.0,
        visited_positions=[(3, 3)],
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.FOOD_LEFT,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=3.0,
                ),
                target_type='gene',
                gene=ActionType.TURN_LEFT,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.CAN_MOVE,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            ),
        ],
    )
    world.creatures = {creature.id: creature}
    world.food_cells = {(2, 3)}
    world.invalidate_spatial_index()

    world.step_world()

    assert creature.last_action == ActionType.TURN_LEFT
    assert creature.facing == Facing.W
    assert (creature.x, creature.y) == (3, 3)

def test_step_skips_eat_when_no_food_is_reachable():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
        move_energy_base_cost=0.0,
        move_energy_area_scale=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=3,
        y=3,
        facing=Facing.E,
        energy=100.0,
        visited_positions=[(3, 3)],
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=3.0,
                ),
                target_type='gene',
                gene=ActionType.EAT,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.CAN_MOVE,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=1.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            ),
        ],
    )
    world.creatures = {creature.id: creature}
    world.invalidate_spatial_index()

    world.step_world()

    assert creature.last_action == ActionType.MOVE
    assert (creature.x, creature.y) == (4, 3)

def test_stateful_program_executes_move_move_turn_sequence():
    params = Parameters(
        world_width=10,
        world_height=10,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
        move_energy_base_cost=0.0,
        move_energy_area_scale=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=2,
        y=2,
        facing=Facing.E,
        energy=100.0,
        visited_positions=[(2, 2)],
        chromosome=[
            Unit(
                promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=0.0, base_strength=5.0),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=0,
                next_state=1,
            ),
            Unit(
                promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=0.0, base_strength=5.0),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=1,
                next_state=2,
            ),
            Unit(
                promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=0.0, base_strength=5.0),
                target_type='gene',
                gene=ActionType.TURN_RIGHT,
                source_state=2,
                next_state=0,
            ),
        ],
    )
    world.creatures = {creature.id: creature}
    world.invalidate_spatial_index()

    world.step_world()
    assert creature.last_action == ActionType.MOVE
    assert (creature.x, creature.y) == (3, 2)
    assert creature.program_state == 1

    world.step_world()
    assert creature.last_action == ActionType.MOVE
    assert (creature.x, creature.y) == (4, 2)
    assert creature.program_state == 2

    world.step_world()
    assert creature.last_action == ActionType.TURN_RIGHT
    assert (creature.x, creature.y) == (4, 2)
    assert creature.facing == Facing.S
    assert creature.program_state == 0

def test_state_signals_can_drive_branching_rules():
    params = Parameters(
        world_width=8,
        world_height=8,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=3,
        y=3,
        facing=Facing.N,
        energy=100.0,
        program_state=2,
        state_ticks=3,
        last_action_success=True,
        visited_positions=[(3, 3)],
        chromosome=[
            Unit(
                promoter=Promoter(signal_id=SignalId.CURRENT_STATE, compare_op=CompareOp.EQ, threshold=2.0, base_strength=2.0),
                target_type='gene',
                gene=ActionType.TURN_LEFT,
            ),
            Unit(
                promoter=Promoter(signal_id=SignalId.STATE_TICKS, compare_op=CompareOp.GE, threshold=3.0, base_strength=3.0),
                target_type='gene',
                gene=ActionType.TURN_RIGHT,
            ),
        ],
    )
    world.creatures = {creature.id: creature}
    world.invalidate_spatial_index()

    world.step_world()

    assert creature.last_action == ActionType.TURN_RIGHT
    assert creature.facing == Facing.E

def test_legacy_reactive_genome_keeps_straight_path_without_turn_injection():
    params = Parameters(
        world_width=20,
        world_height=12,
        initial_creature_count=0,
        max_creatures=1,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        energy_per_tick=0.0,
        move_energy_base_cost=0.0,
        move_energy_area_scale=0.0,
    )
    world = World(params)
    world.initialize_default()

    creature = Creature(
        id=1,
        x=3,
        y=5,
        facing=Facing.E,
        energy=100.0,
        visited_positions=[(3, 5)],
        chromosome=[
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.CAN_MOVE,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=2.5,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
            ),
        ],
    )
    world.creatures = {creature.id: creature}
    world.invalidate_spatial_index()

    for _ in range(7):
        world.step_world()

    assert creature.last_action == ActionType.MOVE
    assert creature.facing == Facing.E
    assert (creature.x, creature.y) == (10, 5)
    assert creature.straight_move_streak == 7

def test_internal_state_count_limits_generated_states():
    from gasp.app.sim.genome_codec import make_random_genome
    from gasp.app.util.rng import RNG

    params = Parameters(internal_state_count=2)
    genome = make_random_genome(RNG(4), 10, params=params)

    for unit in genome:
        if unit.source_state is not None:
            assert unit.source_state < 2
        if unit.next_state is not None:
            assert unit.next_state < 2

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
        visited_positions=[(2, 2), (3, 2), (4, 2), (4, 3)],
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
        visited_positions=[(3, 3)],
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
    assert next_world.last_epoch_summary['best_unique_positions'] == 4
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


def test_initial_food_spawns_away_from_initial_creatures():
    params = Parameters(
        world_width=20,
        world_height=20,
        initial_creature_count=4,
        max_creatures=4,
        initial_food_count=25,
        initial_toxic_count=0,
        initial_food_min_distance_from_creatures=4,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        seed=7,
        seed_mode=SEED_MODE_FIXED,
    )
    world = World(params)
    world.initialize_default()

    creature_cells = {(creature.x, creature.y) for creature in world.creatures.values() if creature.alive}
    assert creature_cells
    assert world.food_cells

    for fx, fy in world.food_cells:
        nearest = min(abs(fx - cx) + abs(fy - cy) for cx, cy in creature_cells)
        assert nearest >= params.initial_food_min_distance_from_creatures


def test_initial_food_spawns_in_center_region():
    params = Parameters(
        world_width=20,
        world_height=20,
        initial_creature_count=4,
        max_creatures=4,
        initial_food_count=25,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        seed=9,
        seed_mode=SEED_MODE_FIXED,
    )
    world = World(params)
    world.initialize_default()

    assert world.food_cells
    for x, y in world.food_cells:
        assert 5 <= x < 15
        assert 5 <= y < 15


def test_dynamic_food_spawns_in_center_region():
    params = Parameters(
        world_width=20,
        world_height=20,
        initial_creature_count=0,
        max_creatures=0,
        initial_food_count=0,
        initial_toxic_count=0,
        food_spawn_rate=0.0,
        toxic_spawn_rate=0.0,
        seed=11,
        seed_mode=SEED_MODE_FIXED,
    )
    world = World(params)
    world.initialize_default()
    world.add_food(30)

    assert world.food_cells
    for x, y in world.food_cells:
        assert 5 <= x < 15
        assert 5 <= y < 15
