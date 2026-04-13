from enum import Enum, auto

class Facing(Enum):
    N = 0
    E = 1
    S = 2
    W = 3

class CellType(Enum):
    GROUND = 0
    WALL = 1
    BORDER = 2
    FOOD = 3
    TOXIC = 4

class ActionType(Enum):
    MOVE = auto()
    TURN_LEFT = auto()
    TURN_RIGHT = auto()
    EAT = auto()
    GROW_N = auto()
    GROW_E = auto()
    GROW_S = auto()
    GROW_W = auto()
    REPRODUCE = auto()
    IDLE = auto()
    ANALYZE = auto()

class SignalId(Enum):
    AGE = auto()
    ENERGY = auto()
    CURRENT_STATE = auto()
    STATE_TICKS = auto()
    WIDTH = auto()
    HEIGHT = auto()
    AREA = auto()
    PREGNANCIES = auto()
    DISTANCE = auto()
    PREV_ACTION = auto()
    LAST_ACTION_SUCCESS = auto()
    FOOD_COUNT = auto()
    TOXIC_COUNT = auto()
    WALL_COUNT = auto()
    FREE_COUNT = auto()
    PARTNER_COUNT = auto()
    CAN_GROW = auto()
    CAN_MOVE = auto()
    CAN_REPRODUCE = auto()
    CAN_EAT = auto()
    FOOD_AHEAD = auto()
    FOOD_LEFT = auto()
    FOOD_RIGHT = auto()
    WALL_AHEAD = auto()
    WALL_LEFT = auto()
    WALL_RIGHT = auto()
    FREE_AHEAD = auto()
    FREE_LEFT = auto()
    FREE_RIGHT = auto()

class CompareOp(Enum):
    LT = auto()
    LE = auto()
    EQ = auto()
    GE = auto()
    GT = auto()

MAX_CREATURE_SIZE = 10
MAX_INTERNAL_STATES = 8
WORLD_VERSION = "1.0"
