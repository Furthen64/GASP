import json
from dataclasses import dataclass, asdict
from secrets import randbelow

SEED_MODE_FIXED = 'fixed'
SEED_MODE_RANDOM = 'random'
MAX_SEED_VALUE = 2_147_483_647

@dataclass
class Parameters:
    world_width: int = 64
    world_height: int = 42
    tick_speed: float = 0.1
    initial_creature_count: int = 8
    max_creatures: int = 10
    pregnancy_chance: float = 0.2
    food_spawn_rate: float = 0.002
    toxic_spawn_rate: float = 0.001
    mutation_rate: float = 0.05
    crossover_rate: float = 0.7
    reproduction_cost: float = 30.0
    max_age: int = 500
    max_size: int = 10
    fitness_lifetime_weight: float = 1.0
    fitness_distance_weight: float = 0.5
    seed: int = 42
    seed_mode: str = SEED_MODE_RANDOM
    initial_food_count: int = 40
    initial_toxic_count: int = 10
    genome_min_units: int = 4
    genome_max_units: int = 20
    initial_energy: float = 100.0
    energy_per_food: float = 50.0
    energy_per_tick: float = 0.5
    move_energy_base_cost: float = 0.0
    move_energy_area_scale: float = 0.35
    epoch_fitness_reproduction_weight: float = 8.0
    epoch_fitness_survival_weight: float = 0.35
    epoch_fitness_exploration_weight: float = 2.5
    epoch_fitness_efficiency_weight: float = 2.5
    epoch_fitness_food_weight: float = 3.0
    epoch_fitness_toxic_penalty: float = 1.5
    epoch_fitness_move_penalty: float = 0.35

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def generate_seed() -> int:
        return randbelow(MAX_SEED_VALUE + 1)

    def resolve_seed(self) -> int:
        if self.seed_mode == SEED_MODE_RANDOM:
            self.seed = self.generate_seed()
        return int(self.seed)

    @classmethod
    def from_dict(cls, d):
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in d.items() if k in fields}
        seed_mode = kwargs.get('seed_mode', SEED_MODE_RANDOM)
        if seed_mode not in (SEED_MODE_FIXED, SEED_MODE_RANDOM):
            kwargs['seed_mode'] = SEED_MODE_RANDOM
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
