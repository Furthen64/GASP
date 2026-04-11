import json
from gasp.app.sim.constants import CellType, Facing, ActionType, SignalId, CompareOp
from gasp.app.sim.creature import Creature, make_creature
from gasp.app.sim.genetics import DEFAULT_MODULES
from gasp.app.sim.sensing import compute_sensed
from gasp.app.sim.actions import execute_action
from gasp.app.sim.fitness import update_fitness, compute_fitness
from gasp.app.sim.history import WorldHistory
from gasp.app.util.rng import RNG
from gasp.app.util.math_helpers import rect_cells

class World:
    def __init__(self, params, seed=42):
        self.params = params
        self.width = params.world_width
        self.height = params.world_height
        self.terrain = {}  # (x,y) -> CellType, defaults to GROUND
        self.food_cells = set()
        self.toxic_cells = set()
        self.creatures = {}  # id -> Creature
        self.step = 0
        self.rng = RNG(seed)
        self.pending_births = []
        self.history = WorldHistory()

    def initialize_default(self):
        """Add border walls, initial food/toxic, and seed creatures."""
        # Border walls
        for x in range(self.width):
            self.terrain[(x, 0)] = CellType.BORDER
            self.terrain[(x, self.height - 1)] = CellType.BORDER
        for y in range(self.height):
            self.terrain[(0, y)] = CellType.BORDER
            self.terrain[(self.width - 1, y)] = CellType.BORDER

        # Initial food and toxic
        self.add_food(self.params.initial_food_count)
        self.add_toxic(self.params.initial_toxic_count)

        # Seed creatures
        from gasp.app.util.ids import CREATURE_ID_GEN
        positions = [
            (2, 2), (self.width - 3, 2),
            (2, self.height - 3), (self.width - 3, self.height - 3)
        ]
        for i in range(self.params.initial_creature_count):
            px, py = positions[i % len(positions)]
            # Find free cell near position
            for dx in range(5):
                for dy in range(5):
                    tx, ty = px + dx, py + dy
                    if self.is_cell_free(tx, ty):
                        c = make_creature(self.rng, self.params, birth_step=0, x=tx, y=ty)
                        self.creatures[c.id] = c
                        break
                else:
                    continue
                break

    def add_food(self, n):
        """Spawn n food cells on free ground."""
        free_cells = self._free_ground_cells()
        self.rng.shuffle(free_cells)
        placed = 0
        for cell in free_cells:
            if placed >= n:
                break
            self.food_cells.add(cell)
            placed += 1

    def add_toxic(self, n):
        """Spawn n toxic cells on free ground."""
        free_cells = self._free_ground_cells()
        self.rng.shuffle(free_cells)
        placed = 0
        for cell in free_cells:
            if placed >= n:
                break
            if cell not in self.food_cells:
                self.toxic_cells.add(cell)
                placed += 1

    def _free_ground_cells(self):
        """Return list of all ground cells that are free."""
        occupied = self.cells_occupied_by_creatures()
        result = []
        for x in range(1, self.width - 1):
            for y in range(1, self.height - 1):
                if (x, y) not in self.terrain and (x, y) not in occupied:
                    if (x, y) not in self.food_cells and (x, y) not in self.toxic_cells:
                        result.append((x, y))
        return result

    def get_cell_type(self, x, y) -> CellType:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return CellType.BORDER
        if (x, y) in self.terrain:
            return self.terrain[(x, y)]
        if (x, y) in self.food_cells:
            return CellType.FOOD
        if (x, y) in self.toxic_cells:
            return CellType.TOXIC
        return CellType.GROUND

    def is_cell_free(self, x, y) -> bool:
        """Return True if cell has no wall, no creature, not border."""
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return False
        ct = self.get_cell_type(x, y)
        if ct in (CellType.WALL, CellType.BORDER):
            return False
        occupied = self.cells_occupied_by_creatures()
        return (x, y) not in occupied

    def get_creature_at(self, x, y):
        """Return creature occupying cell (x,y) or None."""
        for c in self.creatures.values():
            if not c.alive:
                continue
            cells = rect_cells(c.x, c.y, c.width, c.height)
            if (x, y) in cells:
                return c
        return None

    def cells_occupied_by_creatures(self):
        """Return set of all cells occupied by living creatures."""
        result = set()
        for c in self.creatures.values():
            if c.alive:
                result |= rect_cells(c.x, c.y, c.width, c.height)
        return result

    def _evaluate_genome(self, creature) -> ActionType:
        """Evaluate chromosome promoters and return best action."""
        sensed = creature.sensed
        action_scores = {}

        def get_signal_value(signal_id):
            if signal_id == SignalId.AGE:
                return float(creature.age)
            elif signal_id == SignalId.ENERGY:
                return creature.energy
            elif signal_id == SignalId.WIDTH:
                return float(creature.width)
            elif signal_id == SignalId.HEIGHT:
                return float(creature.height)
            elif signal_id == SignalId.AREA:
                return float(creature.width * creature.height)
            elif signal_id == SignalId.PREGNANCIES:
                return float(creature.pregnancies_completed)
            elif signal_id == SignalId.DISTANCE:
                return creature.distance_traveled
            elif signal_id == SignalId.PREV_ACTION:
                return float(creature.last_action.value if creature.last_action else 0)
            elif signal_id == SignalId.FOOD_COUNT:
                return float(sensed.get('food_count', 0))
            elif signal_id == SignalId.TOXIC_COUNT:
                return float(sensed.get('toxic_count', 0))
            elif signal_id == SignalId.WALL_COUNT:
                return float(sensed.get('wall_count', 0))
            elif signal_id == SignalId.FREE_COUNT:
                return float(sensed.get('free_count', 0))
            elif signal_id == SignalId.PARTNER_COUNT:
                return float(sensed.get('partner_count', 0))
            elif signal_id == SignalId.CAN_GROW:
                return float(sensed.get('can_grow', 0))
            elif signal_id == SignalId.CAN_MOVE:
                return float(sensed.get('can_move_forward', 0))
            elif signal_id == SignalId.CAN_REPRODUCE:
                return float(sensed.get('can_reproduce', 0))
            return 0.0

        def compare(value, op, threshold):
            if op == CompareOp.LT:
                return value < threshold
            elif op == CompareOp.LE:
                return value <= threshold
            elif op == CompareOp.EQ:
                return abs(value - threshold) < 0.5
            elif op == CompareOp.GE:
                return value >= threshold
            elif op == CompareOp.GT:
                return value > threshold
            return False

        for unit in creature.chromosome:
            sig_val = get_signal_value(unit.promoter.signal_id)
            fires = compare(sig_val, unit.promoter.compare_op, unit.promoter.threshold)
            if not fires:
                continue
            score = unit.promoter.base_strength
            # Collect actions from this unit
            if unit.target_type == 'gene' and unit.gene is not None:
                action_scores[unit.gene] = action_scores.get(unit.gene, 0.0) + score
            elif unit.target_type == 'module' and unit.module_id in DEFAULT_MODULES:
                module_actions = DEFAULT_MODULES[unit.module_id]
                # Distribute score among module actions
                per_action = score / len(module_actions)
                for at in module_actions:
                    action_scores[at] = action_scores.get(at, 0.0) + per_action

        if not action_scores:
            return ActionType.IDLE
        return max(action_scores, key=action_scores.get)

    def step_world(self):
        """Run one full simulation tick."""
        # 1. Increment step
        self.step += 1

        # 2. Spawn food/toxic per rates
        food_to_spawn = int(self.params.food_spawn_rate * self.width * self.height)
        if food_to_spawn < 1 and self.rng.random() < self.params.food_spawn_rate * self.width * self.height:
            food_to_spawn = 1
        if food_to_spawn > 0:
            self.add_food(food_to_spawn)

        toxic_to_spawn = int(self.params.toxic_spawn_rate * self.width * self.height)
        if toxic_to_spawn < 1 and self.rng.random() < self.params.toxic_spawn_rate * self.width * self.height:
            toxic_to_spawn = 1
        if toxic_to_spawn > 0:
            self.add_toxic(toxic_to_spawn)

        # 3. Determine creature order: sorted by id
        creature_order = sorted(
            [c for c in self.creatures.values() if c.alive],
            key=lambda c: c.id
        )

        # 4. Process each creature
        for creature in creature_order:
            if not creature.alive:
                continue

            # a. age += 1
            creature.age += 1

            # b. compute sensed values
            creature.sensed = compute_sensed(creature, self)

            # c/d. evaluate chromosome -> get best action
            action = self._evaluate_genome(creature)

            # e. execute action
            success = execute_action(action, creature, self)
            creature.last_action = action
            creature.log_action(self.step, action.name, success)

            # f. update energy, fitness
            creature.energy -= self.params.energy_per_tick
            update_fitness(creature)
            fitness = compute_fitness(creature, self.params)
            creature.fitness_history.append(fitness)
            if len(creature.fitness_history) > 200:
                creature.fitness_history.pop(0)

            # Check toxic
            my_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
            if my_cells & self.toxic_cells:
                creature.energy -= 5.0  # Toxic damage

            # g. check death
            if creature.age > self.params.max_age or creature.energy <= 0:
                creature.alive = False
                creature.event_log.append({'step': self.step, 'event': 'died',
                                           'age': creature.age, 'energy': creature.energy})

        # 5. Spawn queued births
        births_to_process = list(self.pending_births)
        self.pending_births.clear()
        for parent_id in births_to_process:
            parent = self.creatures.get(parent_id)
            if parent is None or not parent.alive:
                continue
            # First 2 pregnancies: asexual; after that try sexual
            from gasp.app.sim.reproduction import asexual_reproduce, find_partner, sexual_reproduce
            if parent.pregnancies_completed < 2:
                child = asexual_reproduce(parent, self)
            else:
                partner = find_partner(parent, self)
                if partner:
                    child = sexual_reproduce(parent, partner, self)
                else:
                    child = asexual_reproduce(parent, self)
            if child:
                self.creatures[child.id] = child

        # 6. Update history
        living = sum(1 for c in self.creatures.values() if c.alive)
        self.history.record(self.step, living)

    def to_dict(self):
        terrain_data = {f"{k[0]},{k[1]}": v.name for k, v in self.terrain.items()}
        return {
            'version': '1.0',
            'width': self.width,
            'height': self.height,
            'step': self.step,
            'terrain': terrain_data,
            'food_cells': [list(c) for c in self.food_cells],
            'toxic_cells': [list(c) for c in self.toxic_cells],
            'creatures': {str(k): v.to_dict() for k, v in self.creatures.items()},
            'rng_state': list(self.rng.get_state()),
            'params': self.params.to_dict(),
            'history': self.history.to_dict(),
            'pending_births': self.pending_births,
        }

    @classmethod
    def from_dict(cls, d, params_class=None):
        from gasp.app.persistence.params_io import Parameters
        if params_class is None:
            params_class = Parameters
        params_data = d.get('params', {})
        params = params_class.from_dict(params_data)
        world = cls(params)
        world.width = d.get('width', params.world_width)
        world.height = d.get('height', params.world_height)
        world.step = d.get('step', 0)
        terrain_data = d.get('terrain', {})
        world.terrain = {}
        for key, val in terrain_data.items():
            x, y = map(int, key.split(','))
            world.terrain[(x, y)] = CellType[val]
        world.food_cells = {tuple(c) for c in d.get('food_cells', [])}
        world.toxic_cells = {tuple(c) for c in d.get('toxic_cells', [])}
        world.creatures = {}
        for k, v in d.get('creatures', {}).items():
            c = Creature.from_dict(v)
            world.creatures[c.id] = c
        rng_state = d.get('rng_state')
        if rng_state:
            # Convert back to proper tuple format
            try:
                state = (rng_state[0], tuple(rng_state[1]), rng_state[2])
                world.rng.set_state(state)
            except Exception:
                pass
        world.history = WorldHistory.from_dict(d.get('history', {}))
        world.pending_births = d.get('pending_births', [])
        return world
