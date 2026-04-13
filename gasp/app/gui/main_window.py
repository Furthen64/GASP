from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget,
    QToolBar, QStatusBar, QVBoxLayout, QHBoxLayout,
    QPushButton, QInputDialog, QFileDialog, QLabel, QSpinBox
)
from PySide6.QtCore import Qt, QTimer
from time import perf_counter
from gasp.app.sim.world import World
from gasp.app.persistence.params_io import Parameters
from gasp.app.gui.life_grid_widget import LifeGridWidget
from gasp.app.gui.debug_panel import DebugPanel
from gasp.app.gui.epoch_panel import EpochPanel
from gasp.app.gui.parameter_panel import ParameterPanel
from gasp.app.gui.gamestate_panel import GamestatePanel
from gasp.app.gui.legend_panel import LegendPanel
from gasp.app.util.perf import RollingTimingWindow, TimingSnapshot, humanize_phase_name

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GASP v1 - Genetic Algorithm Simulation Platform")
        self.resize(1200, 800)
        self.params = Parameters()
        self.world = self._create_world()
        self.ui_timings = RollingTimingWindow()
        self._selected_creature = None
        self._epoch_lifespan_enabled = True
        self._epoch_lifespan_seconds = 10
        self._epoch_started_at = perf_counter()
        self._setup_ui()
        self._setup_timer()
        self._update_ui()

    def _create_world(self):
        seed = self.params.resolve_seed()
        world = World(self.params, seed=seed)
        world.initialize_default()
        if hasattr(self, 'param_panel'):
            self.param_panel.sync_seed_value(seed)
        return world

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
        self._speed_spin.setRange(1, 60)
        self._speed_spin.setValue(20)
        self._speed_spin.setSuffix(" ticks/s")
        self._speed_spin.valueChanged.connect(self._on_speed_changed)
        toolbar.addWidget(self._speed_spin)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.grid_widget = LifeGridWidget(self.world)
        self.grid_widget.selected_creature_changed.connect(self._on_creature_selected)
        left_layout.addWidget(self.grid_widget, 1)
        splitter.addWidget(left_panel)

        self.right_tabs = QTabWidget()
        self.debug_panel = DebugPanel()
        self.param_panel = ParameterPanel(self.params)
        self.epoch_panel = EpochPanel()
        self.epoch_panel.lifespan_enabled_changed.connect(self._on_epoch_lifespan_enabled_changed)
        self.epoch_panel.lifespan_seconds_changed.connect(self._on_epoch_lifespan_seconds_changed)
        self.epoch_panel.set_lifespan_settings(self._epoch_lifespan_enabled, self._epoch_lifespan_seconds)
        self.param_panel.params_applied.connect(self._on_params_applied)
        self.right_tabs.addTab(self.epoch_panel, "Epochs")
        self.right_tabs.addTab(self.debug_panel, "Debug")
        self.right_tabs.addTab(self.param_panel, "Parameters")
        self.right_tabs.addTab(LegendPanel(), "Legend")
        splitter.addWidget(self.right_tabs)
        splitter.setSizes([920, 280])

        # Gamestate panel at bottom
        self.gamestate_panel = GamestatePanel()
        self.gamestate_panel.save_requested.connect(self._save_state)
        self.gamestate_panel.load_requested.connect(self._load_state)
        layout.addWidget(self.gamestate_panel)

        # Status bar
        self.status_label = QLabel("Epoch: 1 | Step: 0 | Creatures: 0")
        self.statusBar().addWidget(self.status_label)

        self._auto_run = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_step)

    def _setup_timer(self):
        self._on_speed_changed(self._speed_spin.value())

    def _run_steps(self, n):
        for i in range(n):
            self._advance_world()
            if i % 10 == 0:
                self._update_ui()
        self._update_ui()

    def _advance_world(self):
        if self._epoch_lifespan_reached():
            self._start_next_epoch(reason='lifespan')
            return
        self.world.step_world()
        if self.world.living_creature_count() == 0 and self.world.creatures:
            self._start_next_epoch(reason='extinction')

    def _start_next_epoch(self, reason='extinction'):
        previous_world = self.world
        self.world = previous_world.build_next_epoch_world()
        self._epoch_started_at = perf_counter()
        self.grid_widget.world = self.world
        if not self._auto_select_epoch_winner(previous_world):
            self.grid_widget.clear_selection()
            self._selected_creature = None
            self.debug_panel.clear_creature("No creature selected")
        if reason == 'lifespan':
            status = f"Epoch {self.world.epoch} started after lifespan limit in epoch {previous_world.epoch}"
        else:
            status = f"Epoch {self.world.epoch} started from epoch {previous_world.epoch} elites"
        self.gamestate_panel.set_status(status)
        self.param_panel.sync_seed_value(self.world.seed)

    def _auto_select_epoch_winner(self, previous_world) -> bool:
        if self.right_tabs.currentWidget() is not self.debug_panel:
            return False
        summary = getattr(self.world, 'last_epoch_summary', None) or {}
        best_parent_id = summary.get('best_creature_id')
        selected = None
        if best_parent_id is not None:
            for creature in self.world.creatures.values():
                if creature.parent_ids and creature.parent_ids[0] == best_parent_id:
                    selected = creature
                    break
        if selected is None and self.world.creatures:
            ranked = self.world.ranked_creatures()
            if ranked:
                selected = ranked[0][0]
        if selected is None:
            return False
        self.grid_widget.select_creature(selected)
        return True

    def _run_n_steps(self):
        n, ok = QInputDialog.getInt(self, "Step N", "How many steps?", 100, 1, 100000)
        if ok:
            self._run_steps(n)

    def _reset(self):
        self._set_autoplay(False)
        self.world = self._create_world()
        self._epoch_started_at = perf_counter()
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

    def _epoch_elapsed_seconds(self):
        return max(0.0, perf_counter() - self._epoch_started_at)

    def _epoch_lifespan_reached(self):
        return (
            self._epoch_lifespan_enabled
            and self._epoch_lifespan_seconds > 0
            and self._epoch_elapsed_seconds() >= self._epoch_lifespan_seconds
        )

    def _on_epoch_lifespan_enabled_changed(self, enabled: bool):
        self._epoch_lifespan_enabled = enabled
        self._epoch_started_at = perf_counter()
        self._update_ui()

    def _on_epoch_lifespan_seconds_changed(self, seconds: int):
        self._epoch_lifespan_seconds = seconds
        self._update_ui()

    def _update_ui(self):
        update_start = perf_counter()
        living = sum(1 for c in self.world.creatures.values() if c.alive)
        self.grid_widget.world = self.world
        self.grid_widget.update()
        self.epoch_panel.update_world(
            self.world,
            elapsed_seconds=self._epoch_elapsed_seconds(),
            lifespan_enabled=self._epoch_lifespan_enabled,
            lifespan_seconds=self._epoch_lifespan_seconds,
        )
        if self._selected_creature:
            creature = self.world.creatures.get(self._selected_creature.id)
            if creature:
                self.debug_panel.update_creature(creature, self.world)
        self.ui_timings.add(TimingSnapshot(total_ms=(perf_counter() - update_start) * 1000.0))
        self.debug_panel.update_performance(
            self.world.step_timings.summary(top_n=4),
            self.ui_timings.summary(top_n=2),
            self.grid_widget.paint_timings.summary(top_n=3),
        )
        tick_avg_ms = self.world.step_timings.average_total_ms()
        hot_phases = ", ".join(
            f"{humanize_phase_name(name)} {value:.1f} ms"
            for name, value in self.world.step_timings.top_phases(top_n=2)
        )
        status = f"Epoch: {getattr(self.world, 'epoch', 1)} | Step: {self.world.step} | Creatures: {living}"
        if tick_avg_ms > 0:
            status += f" | Tick avg: {tick_avg_ms:.1f} ms"
        if hot_phases:
            status += f" | Hot: {hot_phases}"
        self.status_label.setText(status)

    def _auto_step(self):
        self._advance_world()
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
                self._epoch_started_at = perf_counter()
                self.grid_widget.world = self.world
                self.grid_widget.clear_selection()
                self._selected_creature = None
                self.debug_panel.clear_creature("No creature selected")
                self.param_panel.sync_seed_value(self.world.seed)
                self._update_ui()
                self.gamestate_panel.set_status(f"Loaded: {path}")
            except Exception as e:
                self.gamestate_panel.set_status(f"Error: {e}")
