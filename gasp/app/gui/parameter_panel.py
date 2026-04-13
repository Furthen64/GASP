from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout,
    QPushButton, QHBoxLayout, QSpinBox, QDoubleSpinBox, QComboBox,
    QGroupBox, QFileDialog
)
from PySide6.QtCore import Signal
from gasp.app.persistence.params_io import (
    Parameters,
    SEED_MODE_FIXED,
    SEED_MODE_RANDOM,
    MAX_SEED_VALUE,
    save_params,
    load_params,
)

class ParameterPanel(QWidget):
    params_applied = Signal(object)

    def __init__(self, params: Parameters, parent=None):
        super().__init__(parent)
        self.params = params
        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

        form_layout = QFormLayout(container)
        self._spinboxes = {}
        self._seed_mode_combo = QComboBox()
        self._seed_mode_combo.addItem("Fixed", SEED_MODE_FIXED)
        self._seed_mode_combo.addItem("Random", SEED_MODE_RANDOM)
        self._seed_mode_combo.currentIndexChanged.connect(self._on_seed_mode_changed)
        form_layout.addRow("Seed Mode:", self._seed_mode_combo)

        int_params = ['world_width', 'world_height', 'initial_creature_count',
                  'max_creatures',
                      'max_age', 'max_size', 'seed', 'initial_food_count',
                      'initial_toxic_count', 'initial_food_min_distance_from_creatures',
                      'initial_creature_spawn_min_distance',
                      'internal_state_count', 'genome_min_units', 'genome_max_units',
                      'runtime_stagnation_window']
        float_params = ['pregnancy_chance', 'food_spawn_rate', 'toxic_spawn_rate',
                        'mutation_rate', 'epoch_elite_mutation_rate', 'crossover_rate', 'reproduction_cost',
                        'initial_energy', 'energy_per_food', 'energy_per_tick',
                        'move_energy_base_cost', 'move_energy_area_scale',
                        'epoch_fitness_reproduction_weight', 'epoch_fitness_survival_weight',
                        'epoch_fitness_exploration_weight', 'epoch_fitness_efficiency_weight',
                        'epoch_fitness_food_weight', 'epoch_fitness_program_complexity_weight',
                        'epoch_fitness_behavior_diversity_weight', 'epoch_fitness_toxic_penalty',
                        'epoch_fitness_move_penalty', 'epoch_fitness_idle_penalty',
                        'runtime_learning_rate', 'runtime_learning_decay',
                        'runtime_reward_action_success', 'runtime_reward_food',
                        'runtime_reward_new_cell', 'runtime_reward_reproduce',
                        'runtime_penalty_failed_action', 'runtime_penalty_idle',
                        'runtime_penalty_blocked_idle',
                        'runtime_penalty_toxic', 'runtime_stagnation_reward_threshold',
                        'runtime_stagnation_nudge']

        for name in int_params:
            val = getattr(self.params, name)
            sb = QSpinBox()
            if name == 'seed':
                sb.setRange(0, MAX_SEED_VALUE)
            else:
                sb.setRange(0, 100000)
            sb.setValue(int(val))
            form_layout.addRow(name.replace('_', ' ').title() + ":", sb)
            self._spinboxes[name] = sb

        for name in float_params:
            val = getattr(self.params, name)
            sb = QDoubleSpinBox()
            sb.setRange(0.0, 10000.0)
            sb.setDecimals(4)
            sb.setSingleStep(0.01)
            sb.setValue(float(val))
            form_layout.addRow(name.replace('_', ' ').title() + ":", sb)
            self._spinboxes[name] = sb

        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self._apply)
        btn_load = QPushButton("Load")
        btn_load.clicked.connect(self._load)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save)
        btn_reset = QPushButton("Reset")
        btn_reset.clicked.connect(self._reset)
        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_load)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_reset)
        layout.addLayout(btn_layout)
        self._sync_seed_mode()

    def _get_current_params(self) -> Parameters:
        kwargs = {}
        for name, sb in self._spinboxes.items():
            kwargs[name] = sb.value()
        kwargs['seed_mode'] = self._seed_mode_combo.currentData()
        return Parameters(**kwargs)

    def _apply(self):
        self.params = self._get_current_params()
        self.params_applied.emit(self.params)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Params", "", "JSON Files (*.json)")
        if path:
            try:
                self.params = load_params(path)
                self._sync_to_ui()
            except Exception as e:
                pass

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Params", "", "JSON Files (*.json)")
        if path:
            try:
                save_params(self._get_current_params(), path)
            except Exception as e:
                pass

    def _reset(self):
        self.params = Parameters()
        self._sync_to_ui()

    def _sync_to_ui(self):
        self._sync_seed_mode()
        for name, sb in self._spinboxes.items():
            val = getattr(self.params, name)
            sb.setValue(val)

    def sync_seed_value(self, seed: int):
        self._spinboxes['seed'].setValue(int(seed))

    def sync_field_value(self, name: str, value):
        spinbox = self._spinboxes.get(name)
        if spinbox is None:
            return
        spinbox.blockSignals(True)
        spinbox.setValue(value)
        spinbox.blockSignals(False)

    def _sync_seed_mode(self):
        seed_mode = getattr(self.params, 'seed_mode', SEED_MODE_FIXED)
        index = self._seed_mode_combo.findData(seed_mode)
        if index >= 0:
            self._seed_mode_combo.setCurrentIndex(index)
        self._on_seed_mode_changed()

    def _on_seed_mode_changed(self):
        is_fixed = self._seed_mode_combo.currentData() == SEED_MODE_FIXED
        self._spinboxes['seed'].setEnabled(is_fixed)
