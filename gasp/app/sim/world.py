from time import perf_counter

from gasp.app.sim.constants import CellType, Facing, ActionType, SignalId, CompareOp
from gasp.app.sim.creature import Creature, make_creature
from gasp.app.sim.genetics import DEFAULT_MODULES
from gasp.app.sim.sensing import compute_sensed
from gasp.app.sim.actions import execute_action
from gasp.app.sim.fitness import update_fitness, compute_fitness
from gasp.app.sim.history import WorldHistory
from gasp.app.util.perf import RollingTimingWindow, TimingSnapshot
from gasp.app.util.rng import RNG
from gasp.app.util.math_helpers import rect_cells

class World:
    def __init__(self, params, seed=None):
        self.params = params
        self.width = params.world_width
        self.height = params.world_height
        self.terrain = {}  # (x,y) -> CellType, defaults to GROUND
        self.food_cells = set()
        self.toxic_cells = set()
        self.creatures = {}  # id -> Creature
        self.step = 0
        if seed is None:
            seed = getattr(params, 'seed', 42)
        self.rng = RNG(seed)
        self.pending_births = []
        self.history = WorldHistory()
        self.step_timings = RollingTimingWindow()
        self.last_step_profile = TimingSnapshot(total_ms=0.0)
        self._spatial_index_dirty = True
        self._occupied_cells_cache = set()
        self._creature_at_cache = {}
        self._creature_count_at_index = -1

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
        initial_creatures = min(self.params.initial_creature_count, self.params.max_creatures)
        for i in range(initial_creatures):
            px, py = positions[i % len(positions)]
            # Find free cell near position
            for dx in range(5):
                for dy in range(5):
                    tx, ty = px + dx, py + dy
                    if self.is_cell_free(tx, ty):
                        c = make_creature(self.rng, self.params, birth_step=0, x=tx, y=ty)
                        self.creatures[c.id] = c
                        self.invalidate_spatial_index()
                        break
                else:
                    continue
                break
        self.invalidate_spatial_index()

    def living_creature_count(self):
        return sum(1 for creature in self.creatures.values() if creature.alive)

    def creature_capacity_remaining(self):
        return max(0, self.params.max_creatures - self.living_creature_count())

    def can_queue_birth(self):
        return self.living_creature_count() + len(self.pending_births) < self.params.max_creatures

    def invalidate_spatial_index(self):
        self._spatial_index_dirty = True

    def _ensure_spatial_index(self):
        if not self._spatial_index_dirty and len(self.creatures) == self._creature_count_at_index:
            return

        occupied = set()
        creature_at = {}
        for creature in self.creatures.values():
            if not creature.alive:
                continue
            for cell in rect_cells(creature.x, creature.y, creature.width, creature.height):
                occupied.add(cell)
                creature_at[cell] = creature

        self._occupied_cells_cache = occupied
        self._creature_at_cache = creature_at
        self._creature_count_at_index = len(self.creatures)
        self._spatial_index_dirty = False

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
        self._ensure_spatial_index()
        return (x, y) not in self._occupied_cells_cache

    def get_creature_at(self, x, y):
        """Return creature occupying cell (x,y) or None."""
        self._ensure_spatial_index()
        return self._creature_at_cache.get((x, y))

    def cells_occupied_by_creatures(self):
        """Return set of all cells occupied by living creatures."""
        self._ensure_spatial_index()
        return self._occupied_cells_cache

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
        return max(action_scores.items(), key=lambda item: item[1])[0]

    def step_world(self):
        """Run one full simulation tick."""
        total_start = perf_counter()
        phase_ms = {}
        self._ensure_spatial_index()

        # 1. Increment step
        self.step += 1

        # 2. Spawn food/toxic per rates
        phase_start = perf_counter()
        food_to_spawn = int(self.params.food_spawn_rate * self.width * self.height)
        if food_to_spawn < 1 and self.rng.random() < self.params.food_spawn_rate * self.width * self.height:
            food_to_spawn = 1
        if food_to_spawn > 0:
            self.add_food(food_to_spawn)
        phase_ms['spawn_food'] = (perf_counter() - phase_start) * 1000.0

        phase_start = perf_counter()
        toxic_to_spawn = int(self.params.toxic_spawn_rate * self.width * self.height)
        if toxic_to_spawn < 1 and self.rng.random() < self.params.toxic_spawn_rate * self.width * self.height:
            toxic_to_spawn = 1
        if toxic_to_spawn > 0:
            self.add_toxic(toxic_to_spawn)
        phase_ms['spawn_toxic'] = (perf_counter() - phase_start) * 1000.0

        # 3. Determine creature order: sorted by id
        phase_start = perf_counter()
        creature_order = sorted(
            [c for c in self.creatures.values() if c.alive],
            key=lambda c: c.id
        )
        phase_ms['creature_sort'] = (perf_counter() - phase_start) * 1000.0

        sense_ms = 0.0
        evaluate_ms = 0.0
        action_ms = 0.0
        upkeep_ms = 0.0
        toxic_ms = 0.0
        death_ms = 0.0
        any_deaths = False

        # 4. Process each creature
        for creature in creature_order:
            if not creature.alive:
                continue

            # a. age += 1
            creature.age += 1

            # b. compute sensed values
            phase_start = perf_counter()
            creature.sensed = compute_sensed(creature, self)
            sense_ms += (perf_counter() - phase_start) * 1000.0

            # c/d. evaluate chromosome -> get best action
            phase_start = perf_counter()
            action = self._evaluate_genome(creature)
            evaluate_ms += (perf_counter() - phase_start) * 1000.0

            # e. execute action
            phase_start = perf_counter()
            success = execute_action(action, creature, self)
            creature.last_action = action
            creature.log_action(self.step, action.name, success)
            action_ms += (perf_counter() - phase_start) * 1000.0

            # f. update energy, fitness
            phase_start = perf_counter()
            creature.energy -= self.params.energy_per_tick
            update_fitness(creature)
            fitness = compute_fitness(creature, self.params)
            creature.fitness_history.append(fitness)
            if len(creature.fitness_history) > 200:
                creature.fitness_history.pop(0)
            upkeep_ms += (perf_counter() - phase_start) * 1000.0

            # Check toxic
            phase_start = perf_counter()
            my_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
            if my_cells & self.toxic_cells:
                creature.energy -= 5.0  # Toxic damage
            toxic_ms += (perf_counter() - phase_start) * 1000.0

            # g. check death
            phase_start = perf_counter()
            if creature.age > self.params.max_age or creature.energy <= 0:
                creature.alive = False
                any_deaths = True
                creature.event_log.append({'step': self.step, 'event': 'died',
                                           'age': creature.age, 'energy': creature.energy})
            death_ms += (perf_counter() - phase_start) * 1000.0

        if any_deaths:
            self.invalidate_spatial_index()

        phase_ms['creature_sense'] = sense_ms
        phase_ms['creature_evaluate'] = evaluate_ms
        phase_ms['creature_action'] = action_ms
        phase_ms['creature_upkeep'] = upkeep_ms
        phase_ms['creature_toxic'] = toxic_ms
        phase_ms['creature_death'] = death_ms

        # 5. Spawn queued births
        phase_start = perf_counter()
        births_to_process = list(self.pending_births)
        self.pending_births.clear()
        births_created = 0
        living_after_deaths = self.living_creature_count()
        for parent_id in births_to_process:
            if living_after_deaths + births_created >= self.params.max_creatures:
                break
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
                births_created += 1
                self.invalidate_spatial_index()
        phase_ms['births'] = (perf_counter() - phase_start) * 1000.0

        # 6. Update history
        phase_start = perf_counter()
        living = self.living_creature_count()
        self.history.record(self.step, living)
        phase_ms['history'] = (perf_counter() - phase_start) * 1000.0

        total_ms = (perf_counter() - total_start) * 1000.0
        self.last_step_profile = TimingSnapshot(
            total_ms=total_ms,
            phase_ms=phase_ms,
            metadata={
                'living_creatures': living,
                'total_creatures': len(self.creatures),
                'births_created': births_created,
                'creature_capacity_remaining': self.creature_capacity_remaining(),
            },
        )
        self.step_timings.add(self.last_step_profile)

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
