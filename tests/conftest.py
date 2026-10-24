import os

# Tests start the app; don't let startup read the live news feeds.
os.environ.setdefault("TRENDING_WARM_UP", "false")
