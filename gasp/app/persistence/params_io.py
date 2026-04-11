import json
from dataclasses import dataclass, field, asdict

@dataclass
class Parameters:
    world_width: int = 32
    world_height: int = 32
    tick_speed: float = 0.1
    initial_creature_count: int = 4
    food_spawn_rate: float = 0.05
    toxic_spawn_rate: float = 0.01
    mutation_rate: float = 0.05
    crossover_rate: float = 0.7
    reproduction_cost: float = 30.0
    max_age: int = 500
    max_size: int = 10
    fitness_lifetime_weight: float = 1.0
    fitness_distance_weight: float = 0.5
    seed: int = 42
    initial_food_count: int = 50
    initial_toxic_count: int = 10
    genome_min_units: int = 4
    genome_max_units: int = 20
    initial_energy: float = 100.0
    energy_per_food: float = 20.0
    energy_per_tick: float = 0.5

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in d.items() if k in fields}
        return cls(**kwargs)

def save_params(params: Parameters, path: str):
    data = {
        'gasp_version': '1.0',
        'params_version': '1.0',
        'params': params.to_dict(),
    }
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_params(path: str) -> Parameters:
    with open(path, 'r') as f:
        data = json.load(f)
    return Parameters.from_dict(data.get('params', {}))
