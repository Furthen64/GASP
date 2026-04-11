import json
from gasp.app.sim.world import World

def save_gamestate(world: World, path: str):
    data = world.to_dict()
    # Convert RNG state to serializable form
    rng_state = world.rng.get_state()
    # state is (version, internalstate_tuple, gauss_next)
    data['rng_state'] = [rng_state[0], list(rng_state[1]), rng_state[2]]
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_gamestate(path: str) -> World:
    with open(path, 'r') as f:
        data = json.load(f)
    return World.from_dict(data)
