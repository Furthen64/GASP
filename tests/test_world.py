import pytest
from gasp.app.persistence.params_io import Parameters
from gasp.app.sim.world import World
from gasp.app.sim.constants import CellType

@pytest.fixture
def default_world():
    from gasp.app.util.ids import CREATURE_ID_GEN
    CREATURE_ID_GEN.reset(0)
    params = Parameters()
    world = World(params)
    world.initialize_default()
    return world

def test_border_walls(default_world):
    w = default_world
    # Check top and bottom rows
    for x in range(w.width):
        assert w.get_cell_type(x, 0) == CellType.BORDER, f"Top border missing at ({x}, 0)"
        assert w.get_cell_type(x, w.height - 1) == CellType.BORDER, f"Bottom border missing"
    # Check left and right columns
    for y in range(w.height):
        assert w.get_cell_type(0, y) == CellType.BORDER, f"Left border missing at (0, {y})"
        assert w.get_cell_type(w.width - 1, y) == CellType.BORDER, f"Right border missing"

def test_initial_creature_count(default_world):
    living = [c for c in default_world.creatures.values() if c.alive]
    assert len(living) == 4, f"Expected 4 initial creatures, got {len(living)}"

def test_step_increments(default_world):
    w = default_world
    assert w.step == 0
    w.step_world()
    assert w.step == 1
    w.step_world()
    assert w.step == 2

def test_food_no_overlap_walls(default_world):
    w = default_world
    for cell in w.food_cells:
        ct = w.terrain.get(cell)
        assert ct not in (CellType.WALL, CellType.BORDER), \
            f"Food at wall/border cell {cell}"
        x, y = cell
        assert 0 < x < w.width - 1 and 0 < y < w.height - 1, \
            f"Food on border at {cell}"
