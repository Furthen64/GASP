import copy

from gasp.app.sim.genetics import Promoter, Unit, DEFAULT_MODULES
from gasp.app.sim.constants import ActionType, SignalId, CompareOp, MAX_INTERNAL_STATES


def _baseline_locomotion_units() -> list[Unit]:
    return [
        Unit(
            promoter=Promoter(
                signal_id=SignalId.CAN_MOVE,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=2.5,
            ),
            target_type='gene',
            gene=ActionType.MOVE,
        ),
        Unit(
            promoter=Promoter(
                signal_id=SignalId.WALL_AHEAD,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=3.0,
            ),
            target_type='gene',
            gene=ActionType.TURN_RIGHT,
        ),
        Unit(
            promoter=Promoter(
                signal_id=SignalId.FOOD_LEFT,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=3.5,
            ),
            target_type='gene',
            gene=ActionType.TURN_LEFT,
        ),
        Unit(
            promoter=Promoter(
                signal_id=SignalId.FOOD_RIGHT,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=3.5,
            ),
            target_type='gene',
            gene=ActionType.TURN_RIGHT,
        ),
        Unit(
            promoter=Promoter(
                signal_id=SignalId.FOOD_AHEAD,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=4.0,
            ),
            target_type='gene',
            gene=ActionType.MOVE,
        ),
        Unit(
            promoter=Promoter(
                signal_id=SignalId.CAN_EAT,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=4.5,
            ),
            target_type='gene',
            gene=ActionType.EAT,
        ),
    ]


def _starter_behavior_programs(state_count: int) -> list[list[Unit]]:
    programs = [
        [
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.IDLE,
                source_state=0,
                next_state=0,
            ),
        ],
        [
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.CAN_MOVE,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=0,
                next_state=0,
            ),
        ],
        [
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=0,
                next_state=1,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.TURN_RIGHT,
                source_state=1,
                next_state=0,
            ),
        ],
        [
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=0,
                next_state=1,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=1,
                next_state=2,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.MOVE,
                source_state=2,
                next_state=3,
            ),
            Unit(
                promoter=Promoter(
                    signal_id=SignalId.ENERGY,
                    compare_op=CompareOp.GT,
                    threshold=0.0,
                    base_strength=4.0,
                ),
                target_type='gene',
                gene=ActionType.TURN_RIGHT,
                source_state=3,
                next_state=0,
            ),
        ],
    ]
    valid_programs = []
    for program in programs:
        highest_state = max(
            max(unit.source_state or 0, unit.next_state or 0)
            for unit in program
        )
        if highest_state < state_count:
            valid_programs.append(program)
    return valid_programs or [programs[0]]


def make_behavior_program_snippet(rng, params=None) -> list[Unit]:
    state_count = MAX_INTERNAL_STATES if params is None else params.clamped_internal_state_count()
    template = copy.deepcopy(rng.choice(_starter_behavior_programs(state_count)))

    used_states = sorted({
        state
        for unit in template
        for state in (unit.source_state, unit.next_state)
        if state is not None
    })
    available_states = list(range(state_count))
    rng.shuffle(available_states)
    state_map = {
        old_state: available_states[index % len(available_states)]
        for index, old_state in enumerate(used_states)
    }

    snippet = []
    for unit in template:
        new_unit = copy.deepcopy(unit)
        if new_unit.source_state is not None:
            new_unit.source_state = state_map[new_unit.source_state]
        if new_unit.next_state is not None:
            new_unit.next_state = state_map[new_unit.next_state]
        new_unit.promoter.base_strength = max(0.5, min(10.0, new_unit.promoter.base_strength + ((rng.random() - 0.5) * 1.5)))
        snippet.append(validate_unit(new_unit, state_count=state_count))
    return snippet

def encode_unit(unit: Unit) -> dict:
    return {
        'promoter': {
            'signal_id': unit.promoter.signal_id.name,
            'compare_op': unit.promoter.compare_op.name,
            'threshold': unit.promoter.threshold,
            'base_strength': unit.promoter.base_strength,
        },
        'target_type': unit.target_type,
        'gene': unit.gene.name if unit.gene is not None else None,
        'module_id': unit.module_id,
        'source_state': unit.source_state,
        'next_state': unit.next_state,
    }

def decode_unit(d: dict) -> Unit:
    try:
        if not isinstance(d, dict):
            raise ValueError("Not a dict")
        p = d.get('promoter', {})
        if not isinstance(p, dict):
            p = {}
        signal_id = SignalId[p.get('signal_id', 'ENERGY')]
        compare_op = CompareOp[p.get('compare_op', 'GT')]
        threshold = float(p.get('threshold', 0.0))
        base_strength = float(p.get('base_strength', 1.0))
        promoter = Promoter(signal_id=signal_id, compare_op=compare_op,
                           threshold=threshold, base_strength=base_strength)
        target_type = d.get('target_type', 'gene')
        gene_name = d.get('gene')
        gene = ActionType[gene_name] if gene_name else None
        module_id = d.get('module_id')
        if module_id is not None:
            module_id = int(module_id)
        source_state = d.get('source_state')
        if source_state is not None:
            source_state = int(source_state)
        next_state = d.get('next_state')
        if next_state is not None:
            next_state = int(next_state)
        return validate_unit(Unit(promoter=promoter, target_type=target_type,
                      gene=gene, module_id=module_id,
                      source_state=source_state, next_state=next_state))
    except Exception:
        # Return safe default on any error
        return Unit(promoter=Promoter(), gene=ActionType.IDLE)

def encode_genome(units: list) -> list:
    return [encode_unit(u) for u in units]

def decode_genome(lst: list) -> list:
    if not isinstance(lst, list):
        return []
    return [decode_unit(d) for d in lst]

def make_random_genome(rng, n_units: int = 8, params=None) -> list:
    if n_units <= 0:
        return []

    state_count = MAX_INTERNAL_STATES if params is None else params.clamped_internal_state_count()

    if n_units < 4:
        return list(_baseline_locomotion_units()[:n_units])

    program_units = make_behavior_program_snippet(rng, params=params)
    units = list(program_units)
    signal_ids = list(SignalId)
    compare_ops = list(CompareOp)
    action_types = list(ActionType)
    module_ids = list(DEFAULT_MODULES.keys())
    for _ in range(len(units), n_units):
        promoter = Promoter(
            signal_id=rng.choice(signal_ids),
            compare_op=rng.choice(compare_ops),
            threshold=rng.random() * 100.0,
            base_strength=rng.random() * 2.0 + 0.1,
        )
        use_module = rng.random() < 0.3
        if use_module:
            unit = Unit(promoter=promoter, target_type='module',
                       gene=None, module_id=rng.choice(module_ids))
        else:
            unit = Unit(promoter=promoter, target_type='gene',
                       gene=rng.choice(action_types), module_id=None)
        if rng.random() < 0.4:
            unit.source_state = rng.randint(0, state_count - 1)
            if rng.random() < 0.8:
                unit.next_state = rng.randint(0, state_count - 1)
        units.append(validate_unit(unit, state_count=state_count))
    return units

def validate_unit(unit: Unit, state_count: int = MAX_INTERNAL_STATES) -> Unit:
    state_count = max(1, min(MAX_INTERNAL_STATES, int(state_count)))
    if not isinstance(unit.promoter.signal_id, SignalId):
        unit.promoter.signal_id = SignalId.ENERGY
    if not isinstance(unit.promoter.compare_op, CompareOp):
        unit.promoter.compare_op = CompareOp.GT
    unit.promoter.threshold = max(0.0, min(1000.0, float(unit.promoter.threshold)))
    unit.promoter.base_strength = max(0.0, min(10.0, float(unit.promoter.base_strength)))
    if unit.target_type not in ('gene', 'module'):
        unit.target_type = 'gene'
    if unit.target_type == 'gene' and unit.gene is None:
        unit.gene = ActionType.IDLE
    if unit.target_type == 'module' and unit.module_id not in DEFAULT_MODULES:
        unit.target_type = 'gene'
        unit.gene = ActionType.IDLE
    if unit.source_state is not None:
        unit.source_state = max(0, min(state_count - 1, int(unit.source_state)))
    if unit.next_state is not None:
        unit.next_state = max(0, min(state_count - 1, int(unit.next_state)))
    return unit
