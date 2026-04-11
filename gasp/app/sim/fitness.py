def update_fitness(creature):
    """Update lifetime_ticks contribution."""
    creature.lifetime_ticks += 1

def compute_fitness(creature, params) -> float:
    """Compute fitness score for a creature."""
    fitness = (creature.lifetime_ticks * params.fitness_lifetime_weight +
               creature.distance_traveled * params.fitness_distance_weight)
    return fitness

def projected_fitness(creature, params, n_steps=10) -> list:
    """Project fitness over next n_steps assuming current behavior."""
    results = []
    current = compute_fitness(creature, params)
    for i in range(1, n_steps + 1):
        projected = current + (params.fitness_lifetime_weight * i +
                               params.fitness_distance_weight * i * 0.1)
        results.append(projected)
    return results
