from dataclasses import dataclass, field
from typing import Optional
from gasp.app.sim.constants import ActionType, SignalId, CompareOp

@dataclass
class Promoter:
    signal_id: SignalId = SignalId.ENERGY
    compare_op: CompareOp = CompareOp.GT
    threshold: float = 0.0
    base_strength: float = 1.0

@dataclass
class Unit:
    promoter: Promoter
    target_type: str = 'gene'  # 'gene' or 'module'
    gene: Optional[ActionType] = None
    module_id: Optional[int] = None

DEFAULT_MODULES = {
    0: [ActionType.ANALYZE, ActionType.MOVE],
    1: [ActionType.TURN_LEFT, ActionType.ANALYZE],
    2: [ActionType.EAT, ActionType.MOVE],
    3: [ActionType.GROW_N, ActionType.IDLE],
    4: [ActionType.REPRODUCE, ActionType.IDLE],
}
