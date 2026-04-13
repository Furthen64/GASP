from dataclasses import dataclass, field
from typing import Optional
from gasp.app.sim.constants import Facing, ActionType
from gasp.app.sim.genetics import Unit
from gasp.app.sim.genome_codec import encode_genome, decode_genome
from gasp.app.util.ids import CREATURE_ID_GEN

@dataclass
class Creature:
    id: int
    parent_ids: list = field(default_factory=list)
    generation: int = 0
    birth_step: int = 0
    age: int = 0
    x: int = 0
    y: int = 0
    width: int = 1
    height: int = 1
    facing: Facing = Facing.N
    alive: bool = True
    energy: float = 100.0
    pregnancies_completed: int = 0
    chromosome: list = field(default_factory=list)
    distance_traveled: float = 0.0
    lifetime_ticks: int = 0
    food_eaten: int = 0
    toxic_ticks: int = 0
    move_energy_spent: float = 0.0
    straight_move_streak: int = 0
    idle_ticks: int = 0
    program_state: int = 0
    state_ticks: int = 0
    actions_seen: list = field(default_factory=list)
    states_seen: list = field(default_factory=list)
    visited_positions: list = field(default_factory=list)
    sensed: dict = field(default_factory=dict)
    action_log: list = field(default_factory=list)
    event_log: list = field(default_factory=list)
    debug_color: tuple = (128, 128, 255)
    selected: bool = False
    learned_biases: list = field(default_factory=list)
    reward_history: list = field(default_factory=list)
    reward_trace: float = 0.0
    last_reward: float = 0.0
    blocked_forward_ticks: int = 0
    last_action: Optional[ActionType] = None
    last_action_success: bool = False

    def log_action(self, step, action, success):
        self.action_log.append({'step': step, 'action': action, 'success': success})
        if len(self.action_log) > 20:
            self.action_log.pop(0)

    def to_dict(self):
        return {
            'id': self.id,
            'parent_ids': self.parent_ids,
            'generation': self.generation,
            'birth_step': self.birth_step,
            'age': self.age,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'facing': self.facing.name,
            'alive': self.alive,
            'energy': self.energy,
            'pregnancies_completed': self.pregnancies_completed,
            'chromosome': encode_genome(self.chromosome),
            'distance_traveled': self.distance_traveled,
            'lifetime_ticks': self.lifetime_ticks,
            'food_eaten': self.food_eaten,
            'toxic_ticks': self.toxic_ticks,
            'move_energy_spent': self.move_energy_spent,
            'straight_move_streak': self.straight_move_streak,
            'idle_ticks': self.idle_ticks,
            'program_state': self.program_state,
            'state_ticks': self.state_ticks,
            'actions_seen': self.actions_seen,
            'states_seen': self.states_seen,
            'visited_positions': [list(pos) for pos in self.visited_positions],
            'sensed': self.sensed,
            'action_log': self.action_log,
            'event_log': self.event_log,
            'debug_color': list(self.debug_color),
            'selected': self.selected,
            'learned_biases': self.learned_biases,
            'reward_history': self.reward_history,
            'reward_trace': self.reward_trace,
            'last_reward': self.last_reward,
            'blocked_forward_ticks': self.blocked_forward_ticks,
            'last_action': self.last_action.name if self.last_action else None,
            'last_action_success': self.last_action_success,
        }

    @classmethod
    def from_dict(cls, d):
        c = cls(id=d['id'])
        c.parent_ids = d.get('parent_ids', [])
        c.generation = d.get('generation', 0)
        c.birth_step = d.get('birth_step', 0)
        c.age = d.get('age', 0)
        c.x = d.get('x', 0)
        c.y = d.get('y', 0)
        c.width = d.get('width', 1)
        c.height = d.get('height', 1)
        c.facing = Facing[d.get('facing', 'N')]
        c.alive = d.get('alive', True)
        c.energy = d.get('energy', 100.0)
        c.pregnancies_completed = d.get('pregnancies_completed', 0)
        c.chromosome = decode_genome(d.get('chromosome', []))
        c.distance_traveled = d.get('distance_traveled', 0.0)
        c.lifetime_ticks = d.get('lifetime_ticks', 0)
        c.food_eaten = d.get('food_eaten', 0)
        c.toxic_ticks = d.get('toxic_ticks', 0)
        c.move_energy_spent = d.get('move_energy_spent', 0.0)
        c.straight_move_streak = d.get('straight_move_streak', 0)
        c.idle_ticks = d.get('idle_ticks', 0)
        c.program_state = d.get('program_state', 0)
        c.state_ticks = d.get('state_ticks', 0)
        c.actions_seen = list(d.get('actions_seen', []))
        c.states_seen = list(d.get('states_seen', []))
        if not c.states_seen:
            c.states_seen = [c.program_state]
        c.visited_positions = [tuple(pos) for pos in d.get('visited_positions', [])]
        if not c.visited_positions:
            c.visited_positions = [(c.x, c.y)]
        c.sensed = d.get('sensed', {})
        c.action_log = d.get('action_log', [])
        c.event_log = d.get('event_log', [])
        dc = d.get('debug_color', [128, 128, 255])
        c.debug_color = tuple(dc)
        c.selected = d.get('selected', False)
        c.learned_biases = list(d.get('learned_biases', []))
        c.reward_history = list(d.get('reward_history', []))
        c.reward_trace = d.get('reward_trace', 0.0)
        c.last_reward = d.get('last_reward', 0.0)
        c.blocked_forward_ticks = d.get('blocked_forward_ticks', 0)
        la = d.get('last_action')
        c.last_action = ActionType[la] if la else None
        c.last_action_success = d.get('last_action_success', False)
        return c

def make_creature(rng, params, birth_step=0, x=1, y=1, parent_ids=None, generation=0):
    from gasp.app.sim.genome_codec import make_random_genome
    cid = CREATURE_ID_GEN.next_id()
    n_units = rng.randint(params.genome_min_units, params.genome_max_units)
    genome = make_random_genome(rng, n_units, params=params)
    color = (rng.randint(50, 255), rng.randint(50, 255), rng.randint(50, 255))
    return Creature(
        id=cid,
        parent_ids=parent_ids or [],
        generation=generation,
        birth_step=birth_step,
        x=x,
        y=y,
        facing=Facing.N,
        energy=params.initial_energy,
        chromosome=genome,
        debug_color=color,
        states_seen=[0],
        visited_positions=[(x, y)],
    )
