"""Mode implementations for navigational suggestions job"""

from merino.jobs.navigational_suggestions.modes.local_mode_runner import run_local_mode
from merino.jobs.navigational_suggestions.modes.normal_mode import run_normal_mode

__all__ = ["run_local_mode", "run_normal_mode"]
