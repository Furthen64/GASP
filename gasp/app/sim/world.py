import copy
from time import perf_counter

from gasp.app.sim.constants import CellType, Facing, ActionType, SignalId, CompareOp
from gasp.app.sim.creature import Creature, make_creature
from gasp.app.sim.genetics import DEFAULT_MODULES
from gasp.app.sim.sensing import compute_sensed
from gasp.app.sim.actions import execute_action
from gasp.app.sim.fitness import update_fitness, compute_fitness, compute_fitness_breakdown
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
            if hasattr(params, 'resolve_seed'):
                seed = params.resolve_seed()
            else:
                seed = getattr(params, 'seed', 42)
        self.seed = int(seed)
        self.rng = RNG(seed)
        self.pending_births = []
        self.history = WorldHistory()
        self.step_timings = RollingTimingWindow()
        self.last_step_profile = TimingSnapshot(total_ms=0.0)
        self.epoch = 1
        self.last_epoch_summary = None
        self.epoch_history = []
        self._spatial_index_dirty = True
        self._occupied_cells_cache = set()
        self._creature_at_cache = {}
        self._creature_count_at_index = -1

    def initialize_default(self, seed_creatures=None):
        """Add border walls, initial food/toxic, and seed creatures."""
        # Border walls
        for x in range(self.width):
            self.terrain[(x, 0)] = CellType.BORDER
            self.terrain[(x, self.height - 1)] = CellType.BORDER
        for y in range(self.height):
            self.terrain[(0, y)] = CellType.BORDER
            self.terrain[(self.width - 1, y)] = CellType.BORDER

        # Seed creatures
        positions = [
            (2, 2), (self.width - 3, 2),
            (2, self.height - 3), (self.width - 3, self.height - 3)
        ]
        initial_creatures = min(self.params.initial_creature_count, self.params.max_creatures)
        templates = list(seed_creatures or [])[:initial_creatures]
        for i in range(initial_creatures):
            px, py = positions[i % len(positions)]
            spawned = False
            for dx in range(5):
                for dy in range(5):
                    tx, ty = px + dx, py + dy
                    if self.is_cell_movable_to(tx, ty):
                        if i < len(templates):
                            creature = self._spawn_epoch_creature(templates[i], tx, ty)
                        else:
                            creature = make_creature(self.rng, self.params, birth_step=0, x=tx, y=ty)
                        self.creatures[creature.id] = creature
                        self.invalidate_spatial_index()
                        spawned = True
                        break
                if spawned:
                    break
        self.invalidate_spatial_index()

        # Initial food and toxic
        initial_spawn_cells = {(creature.x, creature.y) for creature in self.creatures.values() if creature.alive}
        min_food_distance = max(0, int(getattr(self.params, 'initial_food_min_distance_from_creatures', 0)))
        self.add_food(
            self.params.initial_food_count,
            avoid_cells=initial_spawn_cells,
            min_distance=min_food_distance,
        )
        self.add_toxic(self.params.initial_toxic_count)

    def _spawn_epoch_creature(self, template, x, y):
        from gasp.app.util.ids import CREATURE_ID_GEN

        return Creature(
            id=CREATURE_ID_GEN.next_id(),
            parent_ids=[template.id],
            generation=template.generation + 1,
            birth_step=0,
            x=x,
            y=y,
            width=1,
            height=1,
            facing=Facing.N,
            energy=self.params.initial_energy,
            chromosome=copy.deepcopy(template.chromosome),
            debug_color=template.debug_color,
            visited_positions=[(x, y)],
        )

    def living_creature_count(self):
        return sum(1 for creature in self.creatures.values() if creature.alive)

    def ranked_creatures(self):
        ranked = [
            (creature, compute_fitness(creature, self.params))
            for creature in self.creatures.values()
        ]
        ranked.sort(
            key=lambda item: (
                item[1],
                item[0].pregnancies_completed,
                item[0].food_eaten,
                len({tuple(pos) for pos in item[0].visited_positions}),
                item[0].distance_traveled,
                item[0].age,
            ),
            reverse=True,
        )
        return ranked

    def build_next_epoch_world(self):
        ranked = self.ranked_creatures()
        requested_elites = self.params.initial_creature_count or 1
        elite_count = min(requested_elites, len(ranked))
        elites = [creature for creature, _fitness in ranked[:elite_count]]
        best_creature, best_fitness = ranked[0] if ranked else (None, 0.0)
        next_seed = self.params.generate_seed() if hasattr(self.params, 'generate_seed') else self.seed + 1
        self.params.seed = int(next_seed)
        next_world = World(self.params, seed=next_seed)
        next_world.epoch = self.epoch + 1
        next_world.epoch_history = list(self.epoch_history)
        next_world.last_epoch_summary = {
            'epoch': self.epoch,
            'seed': self.seed,
            'steps': self.step,
            'population': len(self.creatures),
            'elite_count': len(elites),
            'best_creature_id': best_creature.id if best_creature else None,
            'best_fitness': best_fitness,
            'best_fitness_breakdown': compute_fitness_breakdown(best_creature, self.params) if best_creature else None,
            'best_distance': best_creature.distance_traveled if best_creature else 0.0,
            'best_food_eaten': best_creature.food_eaten if best_creature else 0,
            'best_pregnancies': best_creature.pregnancies_completed if best_creature else 0,
            'best_unique_positions': len({tuple(pos) for pos in best_creature.visited_positions}) if best_creature else 0,
            'best_generation': best_creature.generation if best_creature else 0,
            'elite_ids': [creature.id for creature in elites],
        }
        next_world.epoch_history.append(next_world.last_epoch_summary)
        next_world.initialize_default(seed_creatures=elites)
        return next_world

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

    def add_food(self, n, avoid_cells=None, min_distance=0):
        """Spawn n food cells on free ground."""
        free_cells = self._free_ground_cells()
        if avoid_cells and min_distance > 0:
            free_cells = [
                cell for cell in free_cells
                if self._distance_to_nearest(cell, avoid_cells) >= min_distance
            ]
        center_cells = self._center_region_cells(free_cells)
        if center_cells:
            free_cells = center_cells
        self.rng.shuffle(free_cells)
        placed = 0
        for cell in free_cells:
            if placed >= n:
                break
            self.food_cells.add(cell)
            placed += 1

    def _center_region_cells(self, cells):
        """Prefer food spawns inside the middle area of the map."""
        if not cells:
            return []
        x_min = self.width // 4
        x_max = self.width - x_min
        y_min = self.height // 4
        y_max = self.height - y_min
        return [
            (x, y) for (x, y) in cells
            if x_min <= x < x_max and y_min <= y < y_max
        ]

    def _distance_to_nearest(self, cell, others):
        if not others:
            return float('inf')
        x, y = cell
        return min(abs(x - ox) + abs(y - oy) for ox, oy in others)

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

    def is_cell_movable_to(self, x, y) -> bool:
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

    def _score_actions(self, creature) -> dict[ActionType, float]:
        """Evaluate chromosome promoters and return accumulated action scores."""
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
            elif signal_id == SignalId.CAN_EAT:
                return float(sensed.get('can_eat', 0))
            elif signal_id == SignalId.FOOD_AHEAD:
                return float(sensed.get('food_ahead', 0))
            elif signal_id == SignalId.FOOD_LEFT:
                return float(sensed.get('food_left', 0))
            elif signal_id == SignalId.FOOD_RIGHT:
                return float(sensed.get('food_right', 0))
            elif signal_id == SignalId.WALL_AHEAD:
                return float(sensed.get('wall_ahead', 0))
            elif signal_id == SignalId.WALL_LEFT:
                return float(sensed.get('wall_left', 0))
            elif signal_id == SignalId.WALL_RIGHT:
                return float(sensed.get('wall_right', 0))
            elif signal_id == SignalId.FREE_AHEAD:
                return float(sensed.get('free_ahead', 0))
            elif signal_id == SignalId.FREE_LEFT:
                return float(sensed.get('free_left', 0))
            elif signal_id == SignalId.FREE_RIGHT:
                return float(sensed.get('free_right', 0))
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
            if unit.target_type == 'gene' and unit.gene is not None:
                action_scores[unit.gene] = action_scores.get(unit.gene, 0.0) + score
            elif unit.target_type == 'module' and unit.module_id in DEFAULT_MODULES:
                module_actions = DEFAULT_MODULES[unit.module_id]
                per_action = score / len(module_actions)
                for at in module_actions:
                    action_scores[at] = action_scores.get(at, 0.0) + per_action

        self._apply_exploration_turn_bias(creature, action_scores)

        return action_scores

    def _apply_exploration_turn_bias(self, creature, action_scores: dict[ActionType, float]):
        if creature.straight_move_streak < 6:
            return
        if not creature.sensed.get('can_move_forward', 0):
            return
        if creature.sensed.get('food_ahead', 0) or creature.sensed.get('food_left', 0) or creature.sensed.get('food_right', 0):
            return

        free_left = bool(creature.sensed.get('free_left', 0))
        free_right = bool(creature.sensed.get('free_right', 0))
        if not free_left and not free_right:
            return

        if free_left and not free_right:
            turn_action = ActionType.TURN_LEFT
        elif free_right and not free_left:
            turn_action = ActionType.TURN_RIGHT
        else:
            turn_action = ActionType.TURN_LEFT if (creature.id + self.step + creature.straight_move_streak) % 2 == 0 else ActionType.TURN_RIGHT

        action_scores[turn_action] = max(action_scores.get(turn_action, 0.0), 3.25)

    def _is_action_feasible(self, creature, action: ActionType) -> bool:
        if action == ActionType.MOVE:
            return bool(creature.sensed.get('can_move_forward', 0))
        if action == ActionType.GROW_N:
            return creature.height < self.params.max_size and all(
                self.is_cell_movable_to(cx, creature.y - 1)
                for cx in range(creature.x, creature.x + creature.width)
            )
        if action == ActionType.GROW_S:
            grow_y = creature.y + creature.height
            return creature.height < self.params.max_size and all(
                self.is_cell_movable_to(cx, grow_y)
                for cx in range(creature.x, creature.x + creature.width)
            )
        if action == ActionType.GROW_E:
            grow_x = creature.x + creature.width
            return creature.width < self.params.max_size and all(
                self.is_cell_movable_to(grow_x, cy)
                for cy in range(creature.y, creature.y + creature.height)
            )
        if action == ActionType.GROW_W:
            return creature.width < self.params.max_size and all(
                self.is_cell_movable_to(creature.x - 1, cy)
                for cy in range(creature.y, creature.y + creature.height)
            )
        if action == ActionType.REPRODUCE:
            return bool(creature.sensed.get('can_reproduce', 0)) and self.can_queue_birth()
        if action == ActionType.EAT:
            return bool(creature.sensed.get('can_eat', 0))
        return True

    def _evaluate_genome(self, creature) -> ActionType:
        """Return the highest-scoring action that is currently feasible."""
        action_scores = self._score_actions(creature)

        if not action_scores:
            return ActionType.IDLE

        ranked_actions = sorted(action_scores.items(), key=lambda item: item[1], reverse=True)
        for action, _score in ranked_actions:
            if self._is_action_feasible(creature, action):
                return action
        return ActionType.IDLE

    def _record_action_outcome(self, creature, action: ActionType, success: bool):
        if action == ActionType.MOVE and success:
            creature.straight_move_streak += 1
            return
        if action in (ActionType.TURN_LEFT, ActionType.TURN_RIGHT):
            creature.straight_move_streak = 0
            return
        if action == ActionType.MOVE and not success:
            creature.straight_move_streak = 0

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
            self._record_action_outcome(creature, action, success)
            creature.last_action = action
            creature.log_action(self.step, action.name, success)
            current_position = (creature.x, creature.y)
            if current_position not in creature.visited_positions:
                creature.visited_positions.append(current_position)
            action_ms += (perf_counter() - phase_start) * 1000.0

            # f. update energy, fitness
            phase_start = perf_counter()
            creature.energy -= self.params.energy_per_tick
            update_fitness(creature)
            upkeep_ms += (perf_counter() - phase_start) * 1000.0

            # Check toxic
            phase_start = perf_counter()
            my_cells = rect_cells(creature.x, creature.y, creature.width, creature.height)
            if my_cells & self.toxic_cells:
                creature.toxic_ticks += 1
                creature.energy -= 5.0  # Toxic damage
            fitness_estimate = compute_fitness(creature, self.params)
            creature.fitness_history.append(fitness_estimate)
            if len(creature.fitness_history) > 200:
                creature.fitness_history.pop(0)
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
            'seed': self.seed,
            'epoch': self.epoch,
            'terrain': terrain_data,
            'food_cells': [list(c) for c in self.food_cells],
            'toxic_cells': [list(c) for c in self.toxic_cells],
            'creatures': {str(k): v.to_dict() for k, v in self.creatures.items()},
            'rng_state': list(self.rng.get_state()),
            'params': self.params.to_dict(),
            'history': self.history.to_dict(),
            'pending_births': self.pending_births,
            'last_epoch_summary': self.last_epoch_summary,
            'epoch_history': self.epoch_history,
        }

    @classmethod
    def from_dict(cls, d, params_class=None):
        from gasp.app.persistence.params_io import Parameters
        if params_class is None:
            params_class = Parameters
        params_data = d.get('params', {})
        params = params_class.from_dict(params_data)
        world = cls(params, seed=d.get('seed', getattr(params, 'seed', 42)))
        world.width = d.get('width', params.world_width)
        world.height = d.get('height', params.world_height)
        world.step = d.get('step', 0)
        world.seed = d.get('seed', getattr(params, 'seed', 42))
        world.epoch = d.get('epoch', 1)
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
        world.last_epoch_summary = d.get('last_epoch_summary')
        world.epoch_history = d.get('epoch_history', [])
        return world
