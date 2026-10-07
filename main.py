# Benoit Saint-Moulin
# Traktor Bridge : launcher

import sys
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from traktor_bridge import integrity

    problems = integrity.check()
    if problems:
        sys.exit(integrity.stop(problems, quiet="--export" in sys.argv or "--verify" in sys.argv))
    from traktor_bridge.app import main

    sys.exit(main())
