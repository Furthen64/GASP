import copy
from math import sqrt
from time import perf_counter

from gasp.app.sim.constants import CellType, Facing, ActionType, SignalId, CompareOp
from gasp.app.sim.creature import Creature, make_creature
from gasp.app.sim.genetics import DEFAULT_MODULES
from gasp.app.sim.reproduction import crossover, mutate
from gasp.app.sim.sensing import compute_sensed
from gasp.app.sim.actions import execute_action
from gasp.app.sim.fitness import update_fitness, compute_fitness, compute_fitness_breakdown
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
        self.step_timings = RollingTimingWindow()
        self.last_step_profile = TimingSnapshot(total_ms=0.0)
        self.epoch = 1
        self.last_epoch_summary = None
        self.epoch_history = []
        self._spatial_index_dirty = True
        self._occupied_cells_cache = set()
        self._creature_at_cache = {}
        self._creature_count_at_index = -1

    def initialize_default(self, seed_creatures=None, seed_mutation_rate=None):
        """Add border walls, initial food/toxic, and seed creatures."""
        self._initialize_border_walls()

        # Seed creatures
        initial_creatures = min(self.params.initial_creature_count, self.params.max_creatures)
        templates = list(seed_creatures or [])[:initial_creatures]
        spawn_cells = self._choose_initial_spawn_cells(initial_creatures)
        for index, (tx, ty) in enumerate(spawn_cells):
            if index < len(templates):
                creature = self._spawn_epoch_creature(templates[index], tx, ty, mutation_rate=seed_mutation_rate)
            else:
                creature = make_creature(self.rng, self.params, birth_step=0, x=tx, y=ty)
            self.creatures[creature.id] = creature
            self.invalidate_spatial_index()
        self.invalidate_spatial_index()

        self._spawn_initial_resources()

    def _initialize_border_walls(self):
        for x in range(self.width):
            self.terrain[(x, 0)] = CellType.BORDER
            self.terrain[(x, self.height - 1)] = CellType.BORDER
        for y in range(self.height):
            self.terrain[(0, y)] = CellType.BORDER
            self.terrain[(self.width - 1, y)] = CellType.BORDER

    def _spawn_initial_resources(self):
        initial_spawn_cells = {(creature.x, creature.y) for creature in self.creatures.values() if creature.alive}
        min_food_distance = max(0, int(getattr(self.params, 'initial_food_min_distance_from_creatures', 0)))
        self.add_food(
            self.params.initial_food_count,
            avoid_cells=initial_spawn_cells,
            min_distance=min_food_distance,
        )
        self.add_toxic(self.params.initial_toxic_count)

    def _spawn_epoch_creature(self, template, x, y, mutation_rate=None):
        from gasp.app.util.ids import CREATURE_ID_GEN

        chromosome = (
            mutate(template.chromosome, self.rng, self.params, mutation_rate_override=mutation_rate)
            if mutation_rate is not None and mutation_rate > 0.0
            else copy.deepcopy(template.chromosome)
        )

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
            chromosome=chromosome,
            debug_color=template.debug_color,
            states_seen=[0],
            visited_positions=[(x, y)],
        )

    def _preferred_spawn_cells(self):
        return [
            (2, 2),
            (self.width - 3, 2),
            (2, self.height - 3),
            (self.width - 3, self.height - 3),
            (self.width // 2, self.height // 2),
            (self.width // 2, 2),
            (self.width // 2, self.height - 3),
            (2, self.height // 2),
            (self.width - 3, self.height // 2),
        ]

    def _choose_initial_spawn_cells(self, count):
        if count <= 0:
            return []
        free_cells = self._free_ground_cells()
        self.rng.shuffle(free_cells)
        candidates = []
        seen = set()
        for cell in self._preferred_spawn_cells() + free_cells:
            if cell in seen:
                continue
            if self.get_cell_type(*cell) != CellType.GROUND:
                continue
            seen.add(cell)
            candidates.append(cell)

        requested_distance = max(0, int(getattr(self.params, 'initial_creature_spawn_min_distance', 0)))
        for min_distance in range(requested_distance, -1, -1):
            selected = []
            for cell in candidates:
                if all(self._distance_to_nearest(cell, [other]) >= min_distance for other in selected):
                    selected.append(cell)
                    if len(selected) >= count:
                        return selected
        return candidates[:count]

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
        parent_pool = [creature for creature, _fitness in ranked[:2]]
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
            'elite_count': len(parent_pool),
            'best_creature_id': best_creature.id if best_creature else None,
            'best_selection_score': best_fitness,
            'best_selection_breakdown': compute_fitness_breakdown(best_creature, self.params) if best_creature else None,
            'best_distance': best_creature.distance_traveled if best_creature else 0.0,
            'best_food_eaten': best_creature.food_eaten if best_creature else 0,
            'best_pregnancies': best_creature.pregnancies_completed if best_creature else 0,
            'best_unique_positions': len({tuple(pos) for pos in best_creature.visited_positions}) if best_creature else 0,
            'best_generation': best_creature.generation if best_creature else 0,
            'elite_ids': [creature.id for creature in parent_pool],
            'elite_mutation_rate': self.params.epoch_elite_mutation_rate,
        }
        next_world.epoch_history.append(next_world.last_epoch_summary)
        if not best_creature:
            next_world.initialize_default()
            return next_world

        next_world._initialize_border_walls()
        next_population = next_world._build_next_epoch_population(parent_pool)
        spawn_cells = next_world._choose_initial_spawn_cells(len(next_population))
        for creature, (tx, ty) in zip(next_population, spawn_cells):
            creature.x = tx
            creature.y = ty
            creature.visited_positions = [(tx, ty)]
            next_world.creatures[creature.id] = creature
        next_world.invalidate_spatial_index()
        next_world._spawn_initial_resources()
        return next_world

    def _make_epoch_creature(self, chromosome, parent_ids, generation, debug_color):
        from gasp.app.util.ids import CREATURE_ID_GEN

        return Creature(
            id=CREATURE_ID_GEN.next_id(),
            parent_ids=list(parent_ids),
            generation=generation,
            birth_step=0,
            x=0,
            y=0,
            width=1,
            height=1,
            facing=Facing.N,
            energy=self.params.initial_energy,
            chromosome=chromosome,
            debug_color=debug_color,
            states_seen=[0],
            visited_positions=[(0, 0)],
        )

    def _build_next_epoch_population(self, parent_pool):
        population_size = min(self.params.initial_creature_count, self.params.max_creatures)
        if population_size <= 0 or not parent_pool:
            return []

        best = parent_pool[0]
        second = parent_pool[1] if len(parent_pool) > 1 else None
        mutation_rate = self.params.epoch_elite_mutation_rate
        next_population = [
            self._make_epoch_creature(
                copy.deepcopy(best.chromosome),
                [best.id],
                best.generation + 1,
                best.debug_color,
            )
        ]

        if second and len(next_population) < population_size:
            crossover_one = [copy.deepcopy(unit) for unit in crossover(best.chromosome, second.chromosome, self.rng)]
            next_population.append(
                self._make_epoch_creature(
                    crossover_one,
                    [best.id, second.id],
                    max(best.generation, second.generation) + 1,
                    best.debug_color,
                )
            )

        if second and len(next_population) < population_size:
            crossover_two = [copy.deepcopy(unit) for unit in crossover(second.chromosome, best.chromosome, self.rng)]
            next_population.append(
                self._make_epoch_creature(
                    crossover_two,
                    [best.id, second.id],
                    max(best.generation, second.generation) + 1,
                    second.debug_color,
                )
            )

        while len(next_population) < population_size:
            mutated = mutate(best.chromosome, self.rng, self.params, mutation_rate_override=mutation_rate)
            next_population.append(
                self._make_epoch_creature(
                    mutated,
                    [best.id],
                    best.generation + 1,
                    best.debug_color,
                )
            )

        return next_population

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

    def _get_signal_value(self, creature, signal_id):
        sensed = creature.sensed
        if signal_id == SignalId.AGE:
            return float(creature.age)
        elif signal_id == SignalId.ENERGY:
            return creature.energy
        elif signal_id == SignalId.CURRENT_STATE:
            return float(creature.program_state)
        elif signal_id == SignalId.STATE_TICKS:
            return float(creature.state_ticks)
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
        elif signal_id == SignalId.LAST_ACTION_SUCCESS:
            return float(creature.last_action_success)
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

    def _compare_signal(self, value, op, threshold):
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

    def _matching_units(self, creature, include_stateful: bool | None) -> list:
        self._ensure_runtime_learning_state(creature)
        units = []
        for index, unit in enumerate(creature.chromosome):
            is_stateful = unit.source_state is not None or unit.next_state is not None
            if include_stateful is True and not is_stateful:
                continue
            if include_stateful is False and is_stateful:
                continue
            if unit.source_state is not None and unit.source_state != creature.program_state:
                continue
            signal_value = self._get_signal_value(creature, unit.promoter.signal_id)
            if not self._compare_signal(signal_value, unit.promoter.compare_op, unit.promoter.threshold):
                continue
            units.append((index, unit))
        return units

    def _ensure_runtime_learning_state(self, creature):
        bias_count = len(creature.chromosome)
        current = list(getattr(creature, 'learned_biases', []))
        if len(current) < bias_count:
            current.extend([0.0] * (bias_count - len(current)))
        elif len(current) > bias_count:
            current = current[:bias_count]
        creature.learned_biases = current

    def _unit_runtime_strength(self, creature, unit_index: int, unit) -> float:
        self._ensure_runtime_learning_state(creature)
        return unit.promoter.base_strength + creature.learned_biases[unit_index]

    def _recent_reward_stagnation(self, creature) -> tuple[bool, list[float], list[dict]]:
        window = max(1, int(getattr(self.params, 'runtime_stagnation_window', 5)))
        threshold = float(getattr(self.params, 'runtime_stagnation_reward_threshold', 0.0))
        if len(creature.reward_history) < window:
            return False, [], []
        recent_rewards = creature.reward_history[-window:]
        if any(reward > threshold for reward in recent_rewards):
            return False, recent_rewards, []
        recent_actions = creature.action_log[-window:]
        return True, recent_rewards, recent_actions

    def _stagnation_fallback_candidates(self, creature) -> list[ActionType]:
        if bool(creature.sensed.get('can_move_forward', 0)):
            preferred = [
                ActionType.MOVE,
                ActionType.TURN_LEFT,
                ActionType.TURN_RIGHT,
                ActionType.EAT,
                ActionType.ANALYZE,
            ]
        else:
            preferred = [
                ActionType.TURN_LEFT,
                ActionType.TURN_RIGHT,
                ActionType.EAT,
                ActionType.ANALYZE,
                ActionType.MOVE,
            ]
        return preferred + [
            ActionType.REPRODUCE,
            ActionType.GROW_N,
            ActionType.GROW_E,
            ActionType.GROW_S,
            ActionType.GROW_W,
            ActionType.IDLE,
        ]

    def _choose_stagnation_fallback_action(self, creature, current_action: ActionType, recent_action_names: list[str]) -> ActionType | None:
        repeated_actions = set(recent_action_names)
        for action in self._stagnation_fallback_candidates(creature):
            if action == current_action:
                continue
            if action.name in repeated_actions:
                continue
            if self._is_action_feasible(creature, action):
                return action
        for action in self._stagnation_fallback_candidates(creature):
            if action == current_action:
                continue
            if self._is_action_feasible(creature, action):
                return action
        return None

    def _maybe_override_stagnating_action(self, creature, action: ActionType, next_state: int | None, unit_index: int | None):
        is_stagnating, _recent_rewards, recent_actions = self._recent_reward_stagnation(creature)
        if not is_stagnating:
            return action, next_state, unit_index

        recent_action_names = [entry.get('action') for entry in recent_actions]
        repeat_count = recent_action_names.count(action.name)
        if action != ActionType.IDLE and repeat_count < max(3, len(recent_action_names) - 1):
            return action, next_state, unit_index

        fallback = self._choose_stagnation_fallback_action(creature, action, recent_action_names)
        if fallback is None:
            return action, next_state, unit_index
        return fallback, None, None

    def _stagnation_action_adjustment(self, creature, action: ActionType) -> float:
        is_stagnating, _recent_rewards, recent_actions = self._recent_reward_stagnation(creature)
        if not is_stagnating:
            return 0.0

        nudge = max(0.0, float(getattr(self.params, 'runtime_stagnation_nudge', 0.0)))
        if nudge <= 0.0:
            return 0.0

        recent_action_names = [entry.get('action') for entry in recent_actions]
        repeat_count = recent_action_names.count(action.name)
        window = max(1, len(recent_action_names))
        novelty_bonus = nudge * ((window - repeat_count) / window)
        repeat_penalty = nudge if creature.last_action == action else 0.0
        idle_penalty = nudge * 0.5 if action == ActionType.IDLE else 0.0
        return novelty_bonus - repeat_penalty - idle_penalty

    def _select_stateful_rule(self, creature) -> tuple[ActionType, int | None, int | None]:
        matching_units = self._matching_units(creature, include_stateful=True)
        if not matching_units:
            return ActionType.IDLE, None, None

        ranked_candidates = []
        for unit_index, unit in matching_units:
            base_score = self._unit_runtime_strength(creature, unit_index, unit)
            if unit.target_type == 'gene' and unit.gene is not None:
                ranked_candidates.append((
                    unit.gene,
                    unit.next_state,
                    unit_index,
                    base_score + self._stagnation_action_adjustment(creature, unit.gene),
                ))
            elif unit.target_type == 'module' and unit.module_id in DEFAULT_MODULES:
                module_actions = DEFAULT_MODULES[unit.module_id]
                for action in module_actions:
                    ranked_candidates.append((
                        action,
                        unit.next_state,
                        unit_index,
                        base_score + self._stagnation_action_adjustment(creature, action),
                    ))

        ranked_candidates.sort(key=lambda item: item[3], reverse=True)
        for action, next_state, unit_index, _score in ranked_candidates:
            if self._is_action_feasible(creature, action):
                return action, next_state, unit_index
        return ActionType.IDLE, None, None

    def _score_legacy_actions(self, creature) -> dict[ActionType, tuple[float, int | None]]:
        """Evaluate legacy reactive chromosomes and return accumulated action scores."""
        action_scores = {}
        for unit_index, unit in self._matching_units(creature, include_stateful=False):
            score = self._unit_runtime_strength(creature, unit_index, unit)
            if unit.target_type == 'gene' and unit.gene is not None:
                current_score, current_unit_index = action_scores.get(unit.gene, (0.0, None))
                next_unit_index = unit_index if current_unit_index is None or score >= current_score else current_unit_index
                action_scores[unit.gene] = (current_score + score, next_unit_index)
            elif unit.target_type == 'module' and unit.module_id in DEFAULT_MODULES:
                module_actions = DEFAULT_MODULES[unit.module_id]
                per_action = score / len(module_actions)
                for at in module_actions:
                    current_score, current_unit_index = action_scores.get(at, (0.0, None))
                    next_unit_index = unit_index if current_unit_index is None or per_action >= current_score else current_unit_index
                    action_scores[at] = (current_score + per_action, next_unit_index)
        if action_scores:
            action_scores = {
                action: (score + self._stagnation_action_adjustment(creature, action), unit_index)
                for action, (score, unit_index) in action_scores.items()
            }
        return action_scores

    def _creature_has_stateful_rules(self, creature) -> bool:
        return any(unit.source_state is not None or unit.next_state is not None for unit in creature.chromosome)

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

    def _evaluate_genome(self, creature) -> tuple[ActionType, int | None, int | None]:
        """Return the highest-scoring action that is currently feasible."""
        if self._creature_has_stateful_rules(creature):
            return self._maybe_override_stagnating_action(creature, *self._select_stateful_rule(creature))

        action_scores = self._score_legacy_actions(creature)

        if not action_scores:
            return self._maybe_override_stagnating_action(creature, ActionType.IDLE, None, None)

        ranked_actions = sorted(action_scores.items(), key=lambda item: item[1][0], reverse=True)
        for action, (_score, unit_index) in ranked_actions:
            if self._is_action_feasible(creature, action):
                return self._maybe_override_stagnating_action(creature, action, None, unit_index)
        return self._maybe_override_stagnating_action(creature, ActionType.IDLE, None, None)

    def _compute_runtime_reward(
        self,
        creature,
        action: ActionType,
        success: bool,
        discovered_new_position: bool,
        start_food_eaten: int,
        start_pregnancies: int,
        blocked_forward: bool,
        toxic_hit: bool,
    ) -> float:
        reward = 0.0
        if success:
            reward += self.params.runtime_reward_action_success
        else:
            reward -= self.params.runtime_penalty_failed_action

        if action == ActionType.IDLE:
            reward -= self.params.runtime_penalty_idle
            if blocked_forward:
                reward -= self.params.runtime_penalty_blocked_idle * sqrt(max(1, creature.blocked_forward_ticks))

        if creature.food_eaten > start_food_eaten:
            reward += (creature.food_eaten - start_food_eaten) * self.params.runtime_reward_food

        if creature.pregnancies_completed > start_pregnancies:
            reward += (creature.pregnancies_completed - start_pregnancies) * self.params.runtime_reward_reproduce

        if discovered_new_position:
            reward += self.params.runtime_reward_new_cell

        if toxic_hit:
            reward -= self.params.runtime_penalty_toxic

        return reward

    def _apply_runtime_learning(self, creature, unit_index: int | None, reward: float):
        self._ensure_runtime_learning_state(creature)
        decay = max(0.0, min(1.0, float(self.params.runtime_learning_decay)))
        creature.learned_biases = [bias * decay for bias in creature.learned_biases]
        creature.last_reward = reward
        creature.reward_trace = creature.reward_trace * decay + reward
        creature.reward_history.append(reward)
        if len(creature.reward_history) > 200:
            creature.reward_history.pop(0)
        if unit_index is None or not creature.learned_biases:
            return
        learning_rate = max(0.0, float(self.params.runtime_learning_rate))
        updated_bias = creature.learned_biases[unit_index] + reward * learning_rate
        creature.learned_biases[unit_index] = max(-6.0, min(6.0, updated_bias))

    def _record_action_outcome(self, creature, action: ActionType, success: bool, next_state: int | None):
        creature.last_action_success = success
        if action.name not in creature.actions_seen:
            creature.actions_seen.append(action.name)
        if next_state is not None:
            if creature.program_state == next_state:
                creature.state_ticks += 1
            else:
                creature.program_state = next_state
                creature.state_ticks = 0
        else:
            creature.state_ticks += 1
        if creature.program_state not in creature.states_seen:
            creature.states_seen.append(creature.program_state)

        if action == ActionType.IDLE and success:
            creature.idle_ticks += 1

        blocked_forward = not bool(creature.sensed.get('can_move_forward', 0))
        if blocked_forward and action == ActionType.IDLE:
            creature.blocked_forward_ticks += 1
        elif action in (ActionType.TURN_LEFT, ActionType.TURN_RIGHT) or not blocked_forward:
            creature.blocked_forward_ticks = 0

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
            action, next_state, selected_unit_index = self._evaluate_genome(creature)
            evaluate_ms += (perf_counter() - phase_start) * 1000.0

            # e. execute action
            phase_start = perf_counter()
            start_position = (creature.x, creature.y)
            start_food_eaten = creature.food_eaten
            start_pregnancies = creature.pregnancies_completed
            blocked_forward = not bool(creature.sensed.get('can_move_forward', 0))
            success = execute_action(action, creature, self)
            self._record_action_outcome(creature, action, success, next_state)
            creature.last_action = action
            creature.log_action(self.step, action.name, success)
            current_position = (creature.x, creature.y)
            discovered_new_position = current_position not in creature.visited_positions
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
            toxic_hit = False
            if my_cells & self.toxic_cells:
                creature.toxic_ticks += 1
                creature.energy -= 5.0  # Toxic damage
                toxic_hit = True
            reward = self._compute_runtime_reward(
                creature,
                action,
                success,
                discovered_new_position,
                start_food_eaten,
                start_pregnancies,
                blocked_forward,
                toxic_hit,
            )
            self._apply_runtime_learning(creature, selected_unit_index, reward)
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

        living = self.living_creature_count()

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
        world.pending_births = d.get('pending_births', [])
        summary = d.get('last_epoch_summary')
        if summary and 'best_selection_score' not in summary and 'best_fitness' in summary:
            summary['best_selection_score'] = summary.get('best_fitness')
        if summary and 'best_selection_breakdown' not in summary and 'best_fitness_breakdown' in summary:
            summary['best_selection_breakdown'] = summary.get('best_fitness_breakdown')
        world.last_epoch_summary = summary
        history = d.get('epoch_history', [])
        for item in history:
            if 'best_selection_score' not in item and 'best_fitness' in item:
                item['best_selection_score'] = item.get('best_fitness')
            if 'best_selection_breakdown' not in item and 'best_fitness_breakdown' in item:
                item['best_selection_breakdown'] = item.get('best_fitness_breakdown')
        world.epoch_history = history
        return world
