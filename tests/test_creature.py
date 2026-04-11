import pytest
from gasp.app.persistence.params_io import Parameters
from gasp.app.sim.creature import Creature, make_creature
from gasp.app.sim.world import World
from gasp.app.util.rng import RNG
from gasp.app.util.ids import CREATURE_ID_GEN

@pytest.fixture
def world():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(max_age=5, initial_energy=100.0, energy_per_tick=1.0)
    w = World(params)
    w.initialize_default()
    return w

def test_creature_to_dict_roundtrip():
    CREATURE_ID_GEN.reset(100)
    rng = RNG(42)
    params = Parameters()
    c = make_creature(rng, params, birth_step=1, x=5, y=5)
    d = c.to_dict()
    c2 = Creature.from_dict(d)
    assert c2.id == c.id
    assert c2.x == c.x
    assert c2.y == c.y
    assert c2.energy == c.energy
    assert c2.facing == c.facing
    assert len(c2.chromosome) == len(c.chromosome)
    assert c2.debug_color == c.debug_color

def test_creature_age_increments(world):
    w = world
    living = [c for c in w.creatures.values() if c.alive]
    assert len(living) > 0
    creature = living[0]
    initial_age = creature.age
    w.step_world()
    assert creature.age == initial_age + 1

def test_creature_death_by_age():
    CREATURE_ID_GEN.reset(200)
    # max_age=2, so creature should die after 2 ticks
    params = Parameters(max_age=2, initial_energy=100.0, energy_per_tick=0.1,
                        food_spawn_rate=0.0, toxic_spawn_rate=0.0,
                        initial_food_count=0, initial_toxic_count=0)
    w = World(params)
    w.initialize_default()
    # Run enough steps
    for _ in range(5):
        w.step_world()
    # All original creatures should be dead (age > max_age)
    all_dead = all(not c.alive for c in w.creatures.values()
                   if c.birth_step == 0)
    assert all_dead, "Expected original creatures to die from old age"
