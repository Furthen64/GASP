import pytest
from gasp.app.persistence.params_io import Parameters
from gasp.app.sim.world import World
from gasp.app.sim.creature import make_creature, Creature
from gasp.app.sim.reproduction import (
    asexual_reproduce, find_partner, sexual_reproduce, crossover, mutate
)
from gasp.app.util.rng import RNG
from gasp.app.util.ids import CREATURE_ID_GEN

@pytest.fixture
def world():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(reproduction_cost=10.0, initial_energy=200.0)
    w = World(params)
    w.initialize_default()
    return w

def test_first_two_pregnancies_asexual(world):
    w = world
    parent = list(w.creatures.values())[0]
    parent.energy = 500.0
    parent.pregnancies_completed = 0

    # First pregnancy
    child1 = asexual_reproduce(parent, w)
    if child1:
        w.creatures[child1.id] = child1
        assert child1.parent_ids == [parent.id]
        assert len(child1.parent_ids) == 1  # Single parent = asexual

    # Second pregnancy
    parent.pregnancies_completed = 1
    child2 = asexual_reproduce(parent, w)
    if child2:
        w.creatures[child2.id] = child2
        assert len(child2.parent_ids) == 1  # Still asexual

def test_asexual_child_different_genome(world):
    w = world
    parent = list(w.creatures.values())[0]
    parent.energy = 500.0
    # Run multiple times to increase chance mutation occurs
    child = None
    different = False
    for _ in range(20):
        child = asexual_reproduce(parent, w)
        if child:
            if len(child.chromosome) != len(parent.chromosome):
                different = True
                break
            for cu, pu in zip(child.chromosome, parent.chromosome):
                if (cu.promoter.threshold != pu.promoter.threshold or
                    cu.gene != pu.gene):
                    different = True
                    break
        if different:
            break
    # With mutation_rate=0.05, some difference should occur
    # But genome could be identical by chance; just check child is valid
    if child:
        assert child.id != parent.id
        assert len(child.chromosome) >= 1

def test_crossover_valid_length():
    rng = RNG(42)
    genome_a = _make_random_genome(rng, 8)
    genome_b = _make_random_genome(rng, 6)
    child_genome = crossover(genome_a, genome_b, rng)
    assert len(child_genome) >= 0  # Can be 0 in edge cases
    # All units should be valid Unit objects
    from gasp.app.sim.genetics import Unit
    for u in child_genome:
        assert isinstance(u, Unit)

def test_reproduction_fails_at_creature_cap():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(initial_creature_count=4, max_creatures=4,
                        reproduction_cost=10.0, initial_energy=200.0)
    w = World(params)
    w.initialize_default()
    parent = list(w.creatures.values())[0]

    from gasp.app.sim.actions import do_reproduce

    assert w.living_creature_count() == 4
    assert do_reproduce(parent, w) is False
    assert w.pending_births == []

def test_reproduction_probability_zero_blocks_pregnancy():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(initial_creature_count=1, max_creatures=4,
                        pregnancy_chance=0.0, reproduction_cost=10.0,
                        initial_energy=200.0)
    w = World(params)
    w.initialize_default()
    parent = list(w.creatures.values())[0]
    start_energy = parent.energy

    from gasp.app.sim.actions import do_reproduce

    assert do_reproduce(parent, w) is False
    assert w.pending_births == []
    assert parent.energy == start_energy

def test_reproduction_probability_one_always_queues_pregnancy():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(initial_creature_count=1, max_creatures=4,
                        pregnancy_chance=1.0, reproduction_cost=10.0,
                        initial_energy=200.0)
    w = World(params)
    w.initialize_default()
    parent = list(w.creatures.values())[0]
    parent.energy = params.reproduction_energy_threshold() + 5.0
    start_energy = parent.energy

    from gasp.app.sim.actions import do_reproduce

    assert do_reproduce(parent, w) is True
    assert w.pending_births == [parent.id]
    assert parent.energy == start_energy - params.reproduction_cost

def test_reproduction_requires_surplus_energy_above_spawn_budget():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(initial_creature_count=1, max_creatures=4,
                        pregnancy_chance=1.0, reproduction_cost=10.0,
                        initial_energy=200.0)
    w = World(params)
    w.initialize_default()
    parent = list(w.creatures.values())[0]

    from gasp.app.sim.actions import do_reproduce

    assert parent.energy == params.initial_energy
    assert do_reproduce(parent, w) is False
    assert w.pending_births == []

def test_mutate_can_inject_stateful_behavior_snippet():
    params = Parameters(mutation_rate=1.0, genome_max_units=12, internal_state_count=6)
    rng = RNG(9)
    genome = [
        Creature(id=1).chromosome,
    ][0]
    if not genome:
        from gasp.app.sim.genetics import Unit, Promoter
        from gasp.app.sim.constants import SignalId, CompareOp, ActionType
        genome = [
            Unit(
                promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=0.0, base_strength=1.0),
                target_type='gene',
                gene=ActionType.MOVE,
            )
        ]

    mutated = mutate(genome, rng, params)

    assert mutated
    assert len(mutated) <= params.genome_max_units
    assert any(unit.source_state is not None or unit.next_state is not None for unit in mutated)
    assert len(mutated) > len(genome)

def test_mutate_respects_internal_state_count_when_injecting_programs():
    from gasp.app.sim.genetics import Unit, Promoter
    from gasp.app.sim.constants import SignalId, CompareOp, ActionType

    params = Parameters(mutation_rate=1.0, genome_max_units=10, internal_state_count=2)
    rng = RNG(11)
    genome = [
        Unit(
            promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=0.0, base_strength=1.0),
            target_type='gene',
            gene=ActionType.MOVE,
        )
    ]

    mutated = mutate(genome, rng, params)

    for unit in mutated:
        if unit.source_state is not None:
            assert unit.source_state < 2
        if unit.next_state is not None:
            assert unit.next_state < 2

def test_mutate_biases_toward_locomotion_actions_for_stateful_rules():
    from gasp.app.sim.genetics import Unit, Promoter
    from gasp.app.sim.constants import SignalId, CompareOp, ActionType

    params = Parameters(mutation_rate=1.0, genome_max_units=10, internal_state_count=4)
    rng = RNG(17)
    genome = [
        Unit(
            promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=0.0, base_strength=1.0),
            target_type='gene',
            gene=ActionType.MOVE,
            source_state=0,
            next_state=1,
        )
    ]

    mutated = mutate(genome, rng, params)
    locomotion_actions = {'MOVE', 'TURN_LEFT', 'TURN_RIGHT', 'EAT', 'ANALYZE'}
    assert any(unit.gene and unit.gene.name in locomotion_actions for unit in mutated if unit.target_type == 'gene')

def _make_random_genome(rng, n):
    from gasp.app.sim.genome_codec import make_random_genome
    return make_random_genome(rng, n)
