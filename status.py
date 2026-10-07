from enum import Enum



class Status(Enum):
    NONE = 0
    OK = 1
    WARNING = 2
    ERROR = 3


STATUS_COLORS = {
    Status.NONE:    "#d0d0d0",  # grey
    Status.OK:      "#90ee90",  # green
    Status.WARNING: "#ffd700",  # yellow
    Status.ERROR:   "#ff6b6b",  # red
}
