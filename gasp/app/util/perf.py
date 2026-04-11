from collections import deque
from dataclasses import dataclass, field


@dataclass
class TimingSnapshot:
    total_ms: float
    phase_ms: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, float | int] = field(default_factory=dict)


def humanize_phase_name(name: str) -> str:
    return name.replace('_', ' ')


class RollingTimingWindow:
    def __init__(self, max_samples: int = 120):
        self._samples = deque(maxlen=max_samples)

    def add(self, snapshot: TimingSnapshot):
        self._samples.append(snapshot)

    @property
    def latest(self):
        if not self._samples:
            return None
        return self._samples[-1]

    def average_total_ms(self) -> float:
        if not self._samples:
            return 0.0
        return sum(snapshot.total_ms for snapshot in self._samples) / len(self._samples)

    def average_phase_ms(self) -> dict[str, float]:
        if not self._samples:
            return {}
        totals = {}
        for snapshot in self._samples:
            for phase_name, phase_ms in snapshot.phase_ms.items():
                totals[phase_name] = totals.get(phase_name, 0.0) + phase_ms
        sample_count = len(self._samples)
        return {
            phase_name: total_ms / sample_count
            for phase_name, total_ms in totals.items()
        }

    def top_phases(self, top_n: int = 3, min_ms: float = 0.05) -> list[tuple[str, float]]:
        averages = self.average_phase_ms()
        ranked = sorted(averages.items(), key=lambda item: item[1], reverse=True)
        return [(name, value) for name, value in ranked if value >= min_ms][:top_n]

    def summary(self, top_n: int = 3, min_ms: float = 0.05) -> str:
        if not self._samples:
            return "No timing data yet"

        parts = [f"avg {self.average_total_ms():.1f} ms"]
        hot_phases = self.top_phases(top_n=top_n, min_ms=min_ms)
        if hot_phases:
            hot_text = ", ".join(
                f"{humanize_phase_name(name)} {value:.1f} ms"
                for name, value in hot_phases
            )
            parts.append(f"hot: {hot_text}")
        return " | ".join(parts)