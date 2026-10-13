from __future__ import annotations

import os
from pathlib import Path


def tutorial_workbuddy_home() -> Path:
    """State root for runnable teaching chapters.

    Real WorkBuddy uses ``~/.workbuddy``. This clean-room tutorial defaults
    to ``~/.learn_workbuddy`` so live lesson runs never collide with a user's
    installed app data. Set WORKBUDDY_HOME to override the location.
    """

    return Path(os.environ.get("WORKBUDDY_HOME", "~/.learn_workbuddy")).expanduser()
