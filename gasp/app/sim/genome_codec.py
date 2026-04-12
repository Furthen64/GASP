from gasp.app.sim.genetics import Promoter, Unit, DEFAULT_MODULES
from gasp.app.sim.constants import ActionType, SignalId, CompareOp


def _baseline_locomotion_units() -> list[Unit]:
    return [
        Unit(
            promoter=Promoter(
                signal_id=SignalId.ENERGY,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=2.5,
            ),
            target_type='gene',
            gene=ActionType.MOVE,
        ),
        Unit(
            promoter=Promoter(
                signal_id=SignalId.ENERGY,
                compare_op=CompareOp.GT,
                threshold=0.0,
                base_strength=1.5,
            ),
            target_type='gene',
            gene=ActionType.TURN_RIGHT,
        ),
    ]

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
        return validate_unit(Unit(promoter=promoter, target_type=target_type,
                                  gene=gene, module_id=module_id))
    except Exception:
        # Return safe default on any error
        return Unit(promoter=Promoter(), gene=ActionType.IDLE)

def encode_genome(units: list) -> list:
    return [encode_unit(u) for u in units]

def decode_genome(lst: list) -> list:
    if not isinstance(lst, list):
        return []
    return [decode_unit(d) for d in lst]

def make_random_genome(rng, n_units: int = 8) -> list:
    if n_units <= 0:
        return []

    baseline_units = _baseline_locomotion_units()[:n_units]
    units = list(baseline_units)
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
        units.append(unit)
    return units

def validate_unit(unit: Unit) -> Unit:
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
    return unit
