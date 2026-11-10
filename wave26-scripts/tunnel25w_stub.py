"""A guarded import of wave25's tunnel25w for the regression suite.

tunnel25w's import installs a SplitOut on sys.stdout (its transport discipline);
the suite restores the real stdout right after, keeping the module handle in
`t25w` (its Pipe25, lt13 binding, diag)."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave25-scripts"))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "tunnel25w_phase_a", os.path.join(REPO, "wave25-scripts", "tunnel25w.py"))
t25w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t25w)

sys.stdout = sys.__stdout__   # give the suite its stdout back; t25w keeps its shim
