"""E34: audit_eval.py with one note added to the audit prompt: Harold wants «κωλο-» compounds, so they are not errors.
Usage: same as audit_eval.py (name greek english [--auditor ...])."""
import os
import runpy
import sys

from subtitlekit.pipeline import audit

KEY = "Report only cues with severity 2 or 3."
assert KEY in audit.AUDIT_PROMPT
audit.AUDIT_PROMPT = audit.AUDIT_PROMPT.replace(KEY, "Greek «κωλο-» / «σκατο-» compounds for \"fucking X\" "
                                                "(κωλοπαράθυρο, κωλοκλόουν) are wanted: never report them.\n" + KEY, 1)
EVAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EVAL)
sys.argv[0] = f"{EVAL}/audit_eval.py"
runpy.run_path(f"{EVAL}/audit_eval.py", run_name="__main__")
