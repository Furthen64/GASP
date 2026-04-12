import os
import json
import pytest
from gasp.app.persistence.params_io import Parameters, save_params, load_params
from gasp.app.persistence.gamestate_io import save_gamestate, load_gamestate
from gasp.app.sim.world import World
from gasp.app.util.ids import CREATURE_ID_GEN

SAVE_DIR = os.path.join(os.path.dirname(__file__), '_test_saves')

@pytest.fixture(autouse=True)
def setup_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)
    yield
    # Cleanup
    import shutil
    if os.path.exists(SAVE_DIR):
        shutil.rmtree(SAVE_DIR)

def test_save_load_params():
    params = Parameters(world_width=50, world_height=40, mutation_rate=0.1,
                        max_creatures=77, pregnancy_chance=0.35)
    path = os.path.join(SAVE_DIR, 'test_params.json')
    save_params(params, path)
    loaded = load_params(path)
    assert loaded.world_width == params.world_width
    assert loaded.world_height == params.world_height
    assert loaded.mutation_rate == params.mutation_rate
    assert loaded.max_creatures == params.max_creatures
    assert loaded.pregnancy_chance == params.pregnancy_chance

def test_save_load_gamestate():
    CREATURE_ID_GEN.reset(0)
    params = Parameters()
    world = World(params)
    world.initialize_default()
    # Run a few steps
    for _ in range(3):
        world.step_world()

    path = os.path.join(SAVE_DIR, 'test_gamestate.json')
    save_gamestate(world, path)
    
    loaded_world = load_gamestate(path)
    assert loaded_world.step == world.step
    assert loaded_world.width == world.width
    assert loaded_world.height == world.height
    assert len(loaded_world.creatures) == len(world.creatures)

def test_rng_state_preserved():
    CREATURE_ID_GEN.reset(0)
    params = Parameters()
    world = World(params)
    world.initialize_default()
    world.step_world()

    path = os.path.join(SAVE_DIR, 'test_rng.json')
    save_gamestate(world, path)

    # Generate some values before loading
    pre_load_vals = [world.rng.random() for _ in range(5)]

    loaded_world = load_gamestate(path)
    # After loading, the RNG state should be restored to the saved state
    post_load_vals = [loaded_world.rng.random() for _ in range(5)]

    assert pre_load_vals == post_load_vals, \
        "RNG state should be preserved through save/load"

def test_epoch_metadata_preserved_through_save_load():
    CREATURE_ID_GEN.reset(0)
    params = Parameters(seed=123, seed_mode='fixed')
    world = World(params)
    world.initialize_default()
    world.step_world()
    world.epoch = 3
    world.last_epoch_summary = {
        'epoch': 2,
        'seed': 111,
        'steps': 44,
        'elite_count': 4,
        'best_creature_id': 9,
        'best_fitness': 88.5,
        'best_distance': 13.0,
        'elite_ids': [9, 10, 11, 12],
    }
    world.epoch_history = [world.last_epoch_summary]

    path = os.path.join(SAVE_DIR, 'test_epoch.json')
    save_gamestate(world, path)

    loaded_world = load_gamestate(path)
    assert loaded_world.epoch == 3
    assert loaded_world.seed == world.seed
    assert loaded_world.last_epoch_summary == world.last_epoch_summary
    assert loaded_world.epoch_history == world.epoch_history
