"""
LangGraph probe. The shape is the one most agent systems actually have: a model produces
evidence and a rationale, then CODE adjudicates that evidence against a threshold read
from the environment.

The stub model is deliberate. What is under test is what the checkpointer persists about
the code-side predicate, not anything about the model. Run three times under thread ids
t1, t2, t3 with different values of LG_MIN_EDGE_THRESHOLD.
"""
import os, json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

class S(TypedDict):
    coin: str
    market_price: float
    fair_value: Optional[float]
    rationale: Optional[str]
    action: Optional[str]
    size_usd: Optional[float]
    account_equity: float

def analyst(state: S) -> dict:
    """Stands in for the LLM call: produces evidence + a rationale."""
    fv = state["market_price"] * 1.002          # a 20bp edge
    return {"fair_value": fv,
            "rationale": f"{state['coin']} mispriced vs 4h mean; fair value {fv:.2f}"}

def gate(state: S) -> dict:
    """CODE-SIDE PREDICATE — the thing that actually decides. Threshold from env."""
    thr = float(os.getenv("LG_MIN_EDGE_THRESHOLD", "0.0025"))     # <-- the value that actually decides
    floor = float(os.getenv("LG_MIN_ORDER_SIZE_USD", "3.0"))
    net_edge = (state["fair_value"] - state["market_price"]) / state["market_price"]
    if abs(net_edge) < thr:
        return {"action": "skip", "size_usd": 0.0}
    size = state["account_equity"] * min(abs(net_edge) / 0.03 * 0.25, 0.25)
    if size < floor:
        return {"action": "skip", "size_usd": 0.0}
    return {"action": "trade", "size_usd": size}

g = StateGraph(S)
g.add_node("analyst", analyst)
g.add_node("gate", gate)
g.add_edge(START, "analyst")
g.add_edge("analyst", "gate")
g.add_edge("gate", END)

DB = "checkpoints.sqlite"
with SqliteSaver.from_conn_string(DB) as cp:
    app = g.compile(checkpointer=cp)
    cfg = {"configurable": {"thread_id": os.getenv("THREAD", "t1")}}
    out = app.invoke({"coin": "ETH", "market_price": 3000.0, "account_equity": 5000.0,
                      "fair_value": None, "rationale": None, "action": None, "size_usd": None}, cfg)
    print("THRESHOLD IN FORCE:", os.getenv("LG_MIN_EDGE_THRESHOLD", "0.0025"), "->", json.dumps({k: out[k] for k in ("action", "size_usd")}))
