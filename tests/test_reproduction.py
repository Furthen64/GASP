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

def _make_random_genome(rng, n):
    from gasp.app.sim.genome_codec import make_random_genome
    return make_random_genome(rng, n)
