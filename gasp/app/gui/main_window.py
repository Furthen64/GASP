from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget,
    QToolBar, QStatusBar, QVBoxLayout, QHBoxLayout,
    QPushButton, QInputDialog, QFileDialog, QLabel, QSpinBox
)
from PySide6.QtCore import Qt, QTimer
from gasp.app.sim.world import World
from gasp.app.persistence.params_io import Parameters
from gasp.app.gui.life_grid_widget import LifeGridWidget
from gasp.app.gui.debug_panel import DebugPanel
from gasp.app.gui.parameter_panel import ParameterPanel
from gasp.app.gui.gamestate_panel import GamestatePanel
from gasp.app.gui.legend_panel import LegendPanel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GASP v1 - Genetic Algorithm Simulation Platform")
        self.resize(1200, 800)
        self.params = Parameters()
        self.world = World(self.params)
        self.world.initialize_default()
        self._selected_creature = None
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        # Toolbar
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        for label, steps in [("Step 1", 1), ("Step 5", 5), ("Step 10", 10),
                               ("Step 50", 50), ("Step 100", 100)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, s=steps: self._run_steps(s))
            toolbar.addWidget(btn)
        btn_n = QPushButton("Step N")
        btn_n.clicked.connect(self._run_n_steps)
        toolbar.addWidget(btn_n)
        btn_reset = QPushButton("Reset")
        btn_reset.clicked.connect(self._reset)
        toolbar.addWidget(btn_reset)
        toolbar.addSeparator()

        self._btn_autoplay = QPushButton("Autoplay: Off")
        self._btn_autoplay.clicked.connect(self._toggle_autoplay)
        toolbar.addWidget(self._btn_autoplay)

        toolbar.addWidget(QLabel("Speed"))
        self._speed_spin = QSpinBox()
        self._speed_spin.setRange(1, 10)
        self._speed_spin.setValue(5)
        self._speed_spin.setSuffix(" ticks/s")
        self._speed_spin.valueChanged.connect(self._on_speed_changed)
        toolbar.addWidget(self._speed_spin)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        self.grid_widget = LifeGridWidget(self.world)
        self.grid_widget.selected_creature_changed.connect(self._on_creature_selected)
        splitter.addWidget(self.grid_widget)

        right_tabs = QTabWidget()
        self.debug_panel = DebugPanel()
        self.param_panel = ParameterPanel(self.params)
        self.param_panel.params_applied.connect(self._on_params_applied)
        right_tabs.addTab(self.debug_panel, "Debug")
        right_tabs.addTab(self.param_panel, "Parameters")
        right_tabs.addTab(LegendPanel(), "Legend")
        splitter.addWidget(right_tabs)
        splitter.setSizes([800, 400])

        # Gamestate panel at bottom
        self.gamestate_panel = GamestatePanel()
        self.gamestate_panel.save_requested.connect(self._save_state)
        self.gamestate_panel.load_requested.connect(self._load_state)
        layout.addWidget(self.gamestate_panel)

        # Status bar
        self.status_label = QLabel("Step: 0 | Creatures: 4")
        self.statusBar().addWidget(self.status_label)

        self._auto_run = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_step)

    def _setup_timer(self):
        self._on_speed_changed(self._speed_spin.value())

    def _run_steps(self, n):
        for i in range(n):
            self.world.step_world()
            if i % 10 == 0:
                self._update_ui()
        self._update_ui()

    def _run_n_steps(self):
        n, ok = QInputDialog.getInt(self, "Step N", "How many steps?", 100, 1, 100000)
        if ok:
            self._run_steps(n)

    def _reset(self):
        self._set_autoplay(False)
        self.world = World(self.params)
        self.world.initialize_default()
        self.grid_widget.world = self.world
        self.grid_widget.clear_selection()
        self._selected_creature = None
        self.debug_panel.clear_creature("No creature selected")
        self._update_ui()

    def _on_creature_selected(self, creature_id):
        self._selected_creature = self.world.creatures.get(creature_id)
        if self._selected_creature:
            self.debug_panel.update_creature(self._selected_creature, self.world)
        else:
            selected = self.grid_widget.selected_cell
            if selected is None:
                self.debug_panel.clear_creature("No creature selected")
            else:
                x, y = selected
                self.debug_panel.clear_creature(f"No creature at cell ({x}, {y})")

    def _on_params_applied(self, params):
        self.params = params
        self.world.params = params

    def _update_ui(self):
        living = sum(1 for c in self.world.creatures.values() if c.alive)
        self.status_label.setText(f"Step: {self.world.step} | Creatures: {living}")
        self.grid_widget.world = self.world
        self.grid_widget.update()
        if self._selected_creature:
            creature = self.world.creatures.get(self._selected_creature.id)
            if creature:
                self.debug_panel.update_creature(creature, self.world)

    def _auto_step(self):
        self.world.step_world()
        self._update_ui()

    def _toggle_autoplay(self):
        self._set_autoplay(not self._auto_run)

    def _set_autoplay(self, enabled: bool):
        self._auto_run = enabled
        if enabled:
            self._timer.start()
            self._btn_autoplay.setText("Autoplay: On")
        else:
            self._timer.stop()
            self._btn_autoplay.setText("Autoplay: Off")

    def _on_speed_changed(self, ticks_per_second: int):
        interval_ms = max(1, int(1000 / ticks_per_second))
        self._timer.setInterval(interval_ms)

    def _save_state(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save State", "", "JSON Files (*.json)")
        if path:
            from gasp.app.persistence.gamestate_io import save_gamestate
            try:
                save_gamestate(self.world, path)
                self.gamestate_panel.set_status(f"Saved: {path}")
            except Exception as e:
                self.gamestate_panel.set_status(f"Error: {e}")

    def _load_state(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load State", "", "JSON Files (*.json)")
        if path:
            from gasp.app.persistence.gamestate_io import load_gamestate
            try:
                self.world = load_gamestate(path)
                self.grid_widget.world = self.world
                self.grid_widget.clear_selection()
                self._selected_creature = None
                self.debug_panel.clear_creature("No creature selected")
                self._update_ui()
                self.gamestate_panel.set_status(f"Loaded: {path}")
            except Exception as e:
                self.gamestate_panel.set_status(f"Error: {e}")
