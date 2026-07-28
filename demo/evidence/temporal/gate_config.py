"""The threshold that decides. Deployed alongside the worker, not inside the history.

This is the ordinary way a threshold reaches workflow code: a config module, an env var,
a settings object. Nothing exotic. The question the probe asks is whether Temporal's
event history — the thing its replay guarantee is defined over — carries this value.
"""

MIN_EDGE_THRESHOLD = 0.0025
MIN_ORDER_SIZE_USD = 3.0
