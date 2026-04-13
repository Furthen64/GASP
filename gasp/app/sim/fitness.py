from math import log1p, sqrt


def update_fitness(creature):
    """Update per-tick counters used by epoch fitness."""
    creature.lifetime_ticks += 1


def compute_fitness_breakdown(creature, params) -> dict:
    initial_energy = max(1.0, float(params.initial_energy))
    energy_ratio = max(0.0, creature.energy) / initial_energy
    unique_positions = len({tuple(pos) for pos in creature.visited_positions})
    breakdown = {
        'reproduction': params.epoch_fitness_reproduction_weight * creature.pregnancies_completed,
        'survival': params.epoch_fitness_survival_weight * log1p(max(0, creature.lifetime_ticks)),
        'exploration': params.epoch_fitness_exploration_weight * sqrt(max(0, unique_positions - 1)),
        'distance': params.fitness_distance_weight * sqrt(max(0.0, creature.distance_traveled)),
        'efficiency': params.epoch_fitness_efficiency_weight * energy_ratio,
        'food': params.epoch_fitness_food_weight * creature.food_eaten,
        'toxic_penalty': params.epoch_fitness_toxic_penalty * creature.toxic_ticks,
        'move_penalty': params.epoch_fitness_move_penalty * creature.move_energy_spent,
    }
    breakdown['total'] = (
        breakdown['reproduction'] +
        breakdown['survival'] +
        breakdown['exploration'] +
        breakdown['distance'] +
        breakdown['efficiency'] +
        breakdown['food'] -
        breakdown['toxic_penalty'] -
        breakdown['move_penalty']
    )
    return breakdown


def compute_fitness(creature, params) -> float:
    """Compute epoch fitness score from accumulated creature outcomes."""
    return compute_fitness_breakdown(creature, params)['total']

def projected_fitness(creature, params, n_steps=10) -> list:
    """Project fitness if current epoch state stays unchanged."""
    results = []
    current = compute_fitness(creature, params)
    results.extend([current] * n_steps)
    return results
