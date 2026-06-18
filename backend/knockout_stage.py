"""Public Phase 6 knockout-stage interface."""

try:
    from .knockout_stage_data import *  # noqa: F401,F403
    from .knockout_stage_simulation import *  # noqa: F401,F403
except ImportError:
    from knockout_stage_data import *  # noqa: F401,F403
    from knockout_stage_simulation import *  # noqa: F401,F403
