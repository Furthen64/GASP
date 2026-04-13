from math import log1p, sqrt


def update_fitness(creature):
    """Update per-tick counters used by epoch fitness."""
    creature.lifetime_ticks += 1


def compute_fitness_breakdown(creature, params) -> dict:
    initial_energy = max(1.0, float(params.initial_energy))
    energy_ratio = max(0.0, creature.energy) / initial_energy
    unique_positions = len({tuple(pos) for pos in creature.visited_positions})
    stateful_units = [
        unit for unit in creature.chromosome
        if unit.source_state is not None or unit.next_state is not None
    ]
    stateful_rule_states = {
        state
        for unit in stateful_units
        for state in (unit.source_state, unit.next_state)
        if state is not None
    }
    actions_seen = {action for action in creature.actions_seen if action != 'IDLE'}
    states_seen = set(creature.states_seen or [creature.program_state])
    breakdown = {
        'reproduction': params.epoch_fitness_reproduction_weight * creature.pregnancies_completed,
        'survival': params.epoch_fitness_survival_weight * log1p(max(0, creature.lifetime_ticks)),
        'exploration': params.epoch_fitness_exploration_weight * sqrt(max(0, unique_positions - 1)),
        'distance': params.fitness_distance_weight * sqrt(max(0.0, creature.distance_traveled)),
        'efficiency': params.epoch_fitness_efficiency_weight * energy_ratio,
        'food': params.epoch_fitness_food_weight * creature.food_eaten,
        'program_complexity': params.epoch_fitness_program_complexity_weight * sqrt(max(0.0, len(stateful_units) + len(stateful_rule_states))),
        'behavior_diversity': params.epoch_fitness_behavior_diversity_weight * sqrt(max(0.0, len(actions_seen) + len(states_seen) - 1)),
        'toxic_penalty': params.epoch_fitness_toxic_penalty * creature.toxic_ticks,
        'move_penalty': params.epoch_fitness_move_penalty * creature.move_energy_spent,
        'idle_penalty': params.epoch_fitness_idle_penalty * creature.idle_ticks,
    }
    breakdown['total'] = (
        breakdown['reproduction'] +
        breakdown['survival'] +
        breakdown['exploration'] +
        breakdown['distance'] +
        breakdown['efficiency'] +
        breakdown['food'] +
        breakdown['program_complexity'] +
        breakdown['behavior_diversity'] -
        breakdown['toxic_penalty'] -
        breakdown['move_penalty'] -
        breakdown['idle_penalty']
    )
    return breakdown


def compute_fitness(creature, params) -> float:
    """Compute epoch fitness score from accumulated creature outcomes."""
    return compute_fitness_breakdown(creature, params)['total']
