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
    c.food_eaten = 3
    c.toxic_ticks = 2
    c.move_energy_spent = 4.5
    c.straight_move_streak = 6
    c.idle_ticks = 7
    c.program_state = 3
    c.state_ticks = 4
    c.last_action_success = True
    c.actions_seen = ['MOVE', 'TURN_RIGHT']
    c.states_seen = [0, 3]
    c.visited_positions = [(5, 5), (6, 5), (6, 6)]
    c.learned_biases = [0.5, -0.25]
    c.reward_history = [1.2, -0.4, 0.8]
    c.reward_trace = 1.75
    c.last_reward = -0.4
    c.blocked_forward_ticks = 2
    d = c.to_dict()
    c2 = Creature.from_dict(d)
    assert c2.id == c.id
    assert c2.x == c.x
    assert c2.y == c.y
    assert c2.energy == c.energy
    assert c2.facing == c.facing
    assert len(c2.chromosome) == len(c.chromosome)
    assert c2.debug_color == c.debug_color
    assert c2.food_eaten == 3
    assert c2.toxic_ticks == 2
    assert c2.move_energy_spent == pytest.approx(4.5)
    assert c2.straight_move_streak == 6
    assert c2.idle_ticks == 7
    assert c2.program_state == 3
    assert c2.state_ticks == 4
    assert c2.last_action_success is True
    assert c2.actions_seen == ['MOVE', 'TURN_RIGHT']
    assert c2.states_seen == [0, 3]
    assert c2.visited_positions == [(5, 5), (6, 5), (6, 6)]
    assert c2.learned_biases == pytest.approx([0.5, -0.25])
    assert c2.reward_history == pytest.approx([1.2, -0.4, 0.8])
    assert c2.reward_trace == pytest.approx(1.75)
    assert c2.last_reward == pytest.approx(-0.4)
    assert c2.blocked_forward_ticks == 2

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
