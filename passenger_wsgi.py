#!/usr/bin/env python3

import sys
import os

INTERP = os.path.expanduser("~/env/bin/python3")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.append(os.getcwd())
