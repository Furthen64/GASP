from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTextEdit


class EpochPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        current_group = QGroupBox("Current Epoch")
        current_form = QFormLayout(current_group)
        self._current_labels = {}
        for field in ['Epoch', 'Seed', 'Step', 'Living', 'Total Creatures']:
            label = QLabel('-')
            current_form.addRow(f"{field}:", label)
            self._current_labels[field] = label
        layout.addWidget(current_group)

        last_group = QGroupBox("Last Extinction")
        last_form = QFormLayout(last_group)
        self._last_labels = {}
        for field in ['Epoch', 'Seed', 'Steps Survived', 'Best Creature', 'Best Fitness', 'Best Distance', 'Elite Count']:
            label = QLabel('-')
            last_form.addRow(f"{field}:", label)
            self._last_labels[field] = label
        layout.addWidget(last_group)

        history_group = QGroupBox("Recent Epochs")
        history_layout = QVBoxLayout(history_group)
        self._history_text = QTextEdit()
        self._history_text.setReadOnly(True)
        self._history_text.setMaximumHeight(160)
        history_layout.addWidget(self._history_text)
        layout.addWidget(history_group)
        layout.addStretch()

    def update_world(self, world):
        self._current_labels['Epoch'].setText(str(getattr(world, 'epoch', 1)))
        self._current_labels['Seed'].setText(str(getattr(world, 'seed', '-')))
        self._current_labels['Step'].setText(str(world.step))
        self._current_labels['Living'].setText(str(world.living_creature_count()))
        self._current_labels['Total Creatures'].setText(str(len(world.creatures)))

        summary = getattr(world, 'last_epoch_summary', None) or {}
        self._last_labels['Epoch'].setText(str(summary.get('epoch', '-')))
        self._last_labels['Seed'].setText(str(summary.get('seed', '-')))
        self._last_labels['Steps Survived'].setText(str(summary.get('steps', '-')))
        self._last_labels['Best Creature'].setText(str(summary.get('best_creature_id', '-')))
        best_fitness = summary.get('best_fitness')
        self._last_labels['Best Fitness'].setText('-' if best_fitness is None else f"{best_fitness:.2f}")
        best_distance = summary.get('best_distance')
        self._last_labels['Best Distance'].setText('-' if best_distance is None else f"{best_distance:.2f}")
        self._last_labels['Elite Count'].setText(str(summary.get('elite_count', '-')))

        history_lines = []
        for item in reversed(getattr(world, 'epoch_history', [])[-8:]):
            history_lines.append(
                f"Epoch {item.get('epoch', '?')}: best #{item.get('best_creature_id', '?')} "
                f"fitness {item.get('best_fitness', 0.0):.2f}, carried {item.get('elite_count', 0)}"
            )
        self._history_text.setText("\n".join(history_lines) if history_lines else "No completed epochs yet")