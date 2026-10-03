import sys

from traktor_bridge.app import main

# spawned ANLZ workers import this module again, they must not start a second GUI
if __name__ == "__main__":
    sys.exit(main())
