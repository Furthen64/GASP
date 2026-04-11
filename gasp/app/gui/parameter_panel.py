from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout,
    QPushButton, QHBoxLayout, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFileDialog
)
from PySide6.QtCore import Signal
from gasp.app.persistence.params_io import Parameters, save_params, load_params

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

        int_params = ['world_width', 'world_height', 'initial_creature_count',
                      'max_age', 'max_size', 'seed', 'initial_food_count',
                      'initial_toxic_count', 'genome_min_units', 'genome_max_units']
        float_params = ['tick_speed', 'food_spawn_rate', 'toxic_spawn_rate',
                        'mutation_rate', 'crossover_rate', 'reproduction_cost',
                        'fitness_lifetime_weight', 'fitness_distance_weight',
                        'initial_energy', 'energy_per_food', 'energy_per_tick']

        for name in int_params:
            val = getattr(self.params, name)
            sb = QSpinBox()
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

    def _get_current_params(self) -> Parameters:
        kwargs = {}
        for name, sb in self._spinboxes.items():
            kwargs[name] = sb.value()
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
        for name, sb in self._spinboxes.items():
            val = getattr(self.params, name)
            sb.setValue(val)
