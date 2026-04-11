class HistoryBuffer:
    def __init__(self, max_size=1000):
        self.max_size = max_size
        self._data = []

    def append(self, item):
        self._data.append(item)
        if len(self._data) > self.max_size:
            self._data.pop(0)

    def get_all(self):
        return list(self._data)

    def __len__(self):
        return len(self._data)

    def to_dict(self):
        return {'max_size': self.max_size, 'data': self._data}

    @classmethod
    def from_dict(cls, d):
        buf = cls(max_size=d.get('max_size', 1000))
        buf._data = list(d.get('data', []))
        return buf


class WorldHistory:
    def __init__(self):
        self.step_counts = HistoryBuffer(max_size=10000)
        self.population_counts = HistoryBuffer(max_size=10000)

    def record(self, step, population):
        self.step_counts.append(step)
        self.population_counts.append(population)

    def to_dict(self):
        return {
            'step_counts': self.step_counts.to_dict(),
            'population_counts': self.population_counts.to_dict(),
        }

    @classmethod
    def from_dict(cls, d):
        wh = cls()
        wh.step_counts = HistoryBuffer.from_dict(d.get('step_counts', {}))
        wh.population_counts = HistoryBuffer.from_dict(d.get('population_counts', {}))
        return wh
