from gasp.app.sim.constants import ActionType
from gasp.app.sim.genetics import Unit, Promoter, DEFAULT_MODULES
from gasp.app.sim.genome_codec import validate_unit, make_random_genome, make_behavior_program_snippet
from gasp.app.util.ids import CREATURE_ID_GEN
from gasp.app.util.math_helpers import neighbor_ring


def _weighted_choice(rng, choices):
    total = sum(weight for _value, weight in choices)
    if total <= 0:
        return choices[0][0]
    roll = rng.random() * total
    cumulative = 0.0
    for value, weight in choices:
        cumulative += weight
        if roll <= cumulative:
            return value
    return choices[-1][0]


def _mutated_gene_action(rng, locomotion_bias=True):
    locomotion_weights = [
        (ActionType.MOVE, 6.0),
        (ActionType.TURN_LEFT, 4.5),
        (ActionType.TURN_RIGHT, 4.5),
        (ActionType.EAT, 3.2),
        (ActionType.ANALYZE, 2.2),
        (ActionType.IDLE, 0.35),
        (ActionType.GROW_N, 0.2),
        (ActionType.GROW_E, 0.2),
        (ActionType.GROW_S, 0.2),
        (ActionType.GROW_W, 0.2),
        (ActionType.REPRODUCE, 0.15),
    ]
    default_weights = [
        (ActionType.MOVE, 3.0),
        (ActionType.TURN_LEFT, 2.5),
        (ActionType.TURN_RIGHT, 2.5),
        (ActionType.EAT, 2.0),
        (ActionType.ANALYZE, 1.8),
        (ActionType.IDLE, 0.4),
        (ActionType.GROW_N, 0.5),
        (ActionType.GROW_E, 0.5),
        (ActionType.GROW_S, 0.5),
        (ActionType.GROW_W, 0.5),
        (ActionType.REPRODUCE, 0.3),
    ]
    return _weighted_choice(rng, locomotion_weights if locomotion_bias else default_weights)


def _weighted_choice(rng, choices):
    total = sum(weight for _value, weight in choices)
    if total <= 0:
        return choices[0][0]
    roll = rng.random() * total
    cumulative = 0.0
    for value, weight in choices:
        cumulative += weight
        if roll <= cumulative:
            return value
    return choices[-1][0]


def _mutated_gene_action(rng, locomotion_bias=True):
    locomotion_weights = [
        (ActionType.MOVE, 6.0),
        (ActionType.TURN_LEFT, 4.5),
        (ActionType.TURN_RIGHT, 4.5),
        (ActionType.EAT, 3.2),
        (ActionType.ANALYZE, 2.2),
        (ActionType.IDLE, 0.35),
        (ActionType.GROW_N, 0.2),
        (ActionType.GROW_E, 0.2),
        (ActionType.GROW_S, 0.2),
        (ActionType.GROW_W, 0.2),
        (ActionType.REPRODUCE, 0.15),
    ]
    default_weights = [
        (ActionType.MOVE, 3.0),
        (ActionType.TURN_LEFT, 2.5),
        (ActionType.TURN_RIGHT, 2.5),
        (ActionType.EAT, 2.0),
        (ActionType.ANALYZE, 1.8),
        (ActionType.IDLE, 0.4),
        (ActionType.GROW_N, 0.5),
        (ActionType.GROW_E, 0.5),
        (ActionType.GROW_S, 0.5),
        (ActionType.GROW_W, 0.5),
        (ActionType.REPRODUCE, 0.3),
    ]
    return _weighted_choice(rng, locomotion_weights if locomotion_bias else default_weights)

def choose_child_position(parent, world):
    """Find a free adjacent cell for the child."""
    ring = list(neighbor_ring(parent.x, parent.y, parent.width, parent.height))
    world.rng.shuffle(ring)
    for cx, cy in ring:
        if world.is_cell_movable_to(cx, cy):
            return (cx, cy)
    return None

def crossover(genome_a, genome_b, rng):
    """Unit-boundary crossover between two genomes."""
    if not genome_a:
        return list(genome_b)
    if not genome_b:
        return list(genome_a)
    # Single-point crossover at unit boundary
    point_a = rng.randint(0, len(genome_a))
    point_b = rng.randint(0, len(genome_b))
    child = genome_a[:point_a] + genome_b[point_b:]
    # Ensure minimum length
    if not child:
        child = list(genome_a) if genome_a else list(genome_b)
    return child

def mutate(genome, rng, params):
    """Apply mutations: value replace, disable, duplicate, remove."""
    import copy
    from gasp.app.sim.constants import SignalId, CompareOp
    from gasp.app.sim.genetics import Promoter, Unit
    state_count = params.clamped_internal_state_count()
    genome = [copy.deepcopy(u) for u in genome]
    result = []

    def inject_behavior_snippet(target_genome):
        if len(target_genome) >= params.genome_max_units:
            return target_genome
        snippet = make_behavior_program_snippet(rng, params=params)
        remaining_slots = max(0, params.genome_max_units - len(target_genome))
        snippet = snippet[:remaining_slots]
        insert_at = rng.randint(0, len(target_genome)) if target_genome else 0
        return target_genome[:insert_at] + snippet + target_genome[insert_at:]

    def is_locomotion_rule(unit):
        return unit.target_type == 'gene' and unit.gene in {
            ActionType.MOVE,
            ActionType.TURN_LEFT,
            ActionType.TURN_RIGHT,
            ActionType.EAT,
            ActionType.ANALYZE,
        }

    def is_locomotion_rule(unit):
        return unit.target_type == 'gene' and unit.gene in {
            ActionType.MOVE,
            ActionType.TURN_LEFT,
            ActionType.TURN_RIGHT,
            ActionType.EAT,
            ActionType.ANALYZE,
        }

    for unit in genome:
        r = rng.random()
        if r < params.mutation_rate * 0.2:
            unit.gene = _mutated_gene_action(
                rng,
                locomotion_bias=is_locomotion_rule(unit) or unit.source_state is not None or unit.next_state is not None,
            )
        r2 = rng.random()
        if r2 < params.mutation_rate:
            # Mutate promoter threshold
            unit.promoter.threshold = max(0.0, unit.promoter.threshold + (rng.random() - 0.5) * 20.0)
        r3 = rng.random()
        if r3 < params.mutation_rate:
            # Mutate base_strength
            unit.promoter.base_strength = max(0.0, unit.promoter.base_strength + (rng.random() - 0.5))
        r4 = rng.random()
        if r4 < params.mutation_rate * 0.5:
            # Change signal_id
            unit.promoter.signal_id = rng.choice(list(SignalId))
        r5 = rng.random()
        if r5 < params.mutation_rate * 0.5:
            # Change compare_op
            unit.promoter.compare_op = rng.choice(list(CompareOp))
        r6 = rng.random()
        if r6 < params.mutation_rate * 0.3 and unit.target_type == 'gene':
            unit.gene = _mutated_gene_action(
                rng,
                locomotion_bias=is_locomotion_rule(unit) or unit.source_state is not None or unit.next_state is not None,
            )
        r7 = rng.random()
        if r7 < params.mutation_rate * 0.4:
            unit.source_state = rng.randint(0, state_count - 1) if rng.random() < 0.7 else None
        r8 = rng.random()
        if r8 < params.mutation_rate * 0.4:
            unit.next_state = rng.randint(0, state_count - 1) if rng.random() < 0.8 else None
        result.append(validate_unit(unit, state_count=state_count))
        # Duplicate
        if rng.random() < params.mutation_rate * 0.1:
            import copy
            result.append(validate_unit(copy.deepcopy(unit), state_count=state_count))
    if result and (len(result) < 3 or rng.random() < params.mutation_rate * 0.9):
        result = inject_behavior_snippet(result)
    if result and rng.random() < params.mutation_rate * 0.5:
        stateful_units = [unit for unit in result if unit.source_state is not None or unit.next_state is not None]
        if stateful_units:
            anchor = rng.choice(stateful_units)
            loop_target = anchor.source_state if anchor.source_state is not None else rng.randint(0, state_count - 1)
            for unit in stateful_units:
                if unit.next_state is None and rng.random() < 0.5:
                    unit.next_state = loop_target
                    break
            result = [validate_unit(unit, state_count=state_count) for unit in result]
    if result and not any(unit.source_state is not None or unit.next_state is not None for unit in result):
        result = inject_behavior_snippet(result)
    if not result:
        result = make_random_genome(rng, 4, params=params)
    if len(result) > params.genome_max_units:
        result = result[:params.genome_max_units]
    return result

def asexual_reproduce(parent, world):
    """Create child via self-copy + mutation."""
    from gasp.app.sim.creature import Creature
    pos = choose_child_position(parent, world)
    if pos is None:
        return None
    cx, cy = pos
    child_genome = mutate(list(parent.chromosome), world.rng, world.params)
    cid = CREATURE_ID_GEN.next_id()
    color = (
        world.rng.randint(50, 255),
        world.rng.randint(50, 255),
        world.rng.randint(50, 255),
    )
    child = Creature(
        id=cid,
        parent_ids=[parent.id],
        generation=parent.generation + 1,
        birth_step=world.step,
        x=cx,
        y=cy,
        facing=parent.facing,
        energy=world.params.initial_energy,
        chromosome=child_genome,
        debug_color=color,
    )
    parent.pregnancies_completed += 1
    return child

def find_partner(creature, world):
    """Find another living creature adjacent to this one."""
    from gasp.app.util.math_helpers import neighbor_ring
    ring = neighbor_ring(creature.x, creature.y, creature.width, creature.height)
    for cx, cy in ring:
        c = world.get_creature_at(cx, cy)
        if c and c.id != creature.id and c.alive:
            return c
    return None

def sexual_reproduce(parent_a, parent_b, world):
    """Create child from two parents via crossover + mutation."""
    from gasp.app.sim.creature import Creature
    pos = choose_child_position(parent_a, world)
    if pos is None:
        pos = choose_child_position(parent_b, world)
    if pos is None:
        return None
    cx, cy = pos
    child_genome = crossover(parent_a.chromosome, parent_b.chromosome, world.rng)
    child_genome = mutate(child_genome, world.rng, world.params)
    cid = CREATURE_ID_GEN.next_id()
    color = (
        world.rng.randint(50, 255),
        world.rng.randint(50, 255),
        world.rng.randint(50, 255),
    )
    child = Creature(
        id=cid,
        parent_ids=[parent_a.id, parent_b.id],
        generation=max(parent_a.generation, parent_b.generation) + 1,
        birth_step=world.step,
        x=cx,
        y=cy,
        facing=parent_a.facing,
        energy=world.params.initial_energy,
        chromosome=child_genome,
        debug_color=color,
    )
    parent_a.pregnancies_completed += 1
    parent_b.pregnancies_completed += 1
    return child
