"""Temporal probe.

Temporal is the hardest case for the thesis, because deterministic replay IS its product.
It replays a workflow against its recorded event history and raises on nondeterminism.

The probe asks one question: **is Temporal's replay guarantee sound for re-adjudicating a
different policy?** Not "does Temporal work" — it plainly does — but "what class of
counterfactual does its history support?"

Two workflows, identical decision logic, differing only in whether the decision crosses a
command boundary:

  A. GateWithCommand    — a 'trade' schedules a second activity. The branch is a command.
  B. GateWithoutCommand — the branch only changes the returned payload. No command.

Each is recorded once under one threshold, then replayed with the threshold changed
underneath it. What Temporal does in each case is the finding.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

# The workflow sandbox re-imports modules, which would isolate the config change and hide
# the very thing under test. Passing the config through is what a real deployment does with
# a settings module, and it is the only way to model config resolved outside the history.
with workflow.unsafe.imports_passed_through():
    import gate_config as cfg


@dataclass
class Order:
    market_price: float
    equity: float


@activity.defn
async def analyst(market_price: float) -> float:
    """Stands in for the model call. Marks fair value 20bp above market."""
    return market_price * 1.002


@activity.defn
async def execute_trade(size: float) -> str:
    return f"filled {size:.2f}"


# What the workflow code decided, appended on every execution INCLUDING replays. This is
# the instrument: it lets the probe show what replay actually computed, rather than infer it
# from the absence of an error.
DECIDED: list[str] = []


def _net_edge(fair_value: float, market_price: float) -> float:
    return (fair_value - market_price) / market_price


@workflow.defn
class GateWithCommand:
    @workflow.run
    async def run(self, order: Order) -> dict:
        fair = await workflow.execute_activity(
            analyst, order.market_price, start_to_close_timeout=timedelta(seconds=10)
        )
        edge = _net_edge(fair, order.market_price)
        if abs(edge) < cfg.MIN_EDGE_THRESHOLD:
            DECIDED.append("skip")
            return {"action": "skip", "size": 0.0}
        DECIDED.append("trade")
        size = order.equity * min(abs(edge) / 0.03 * 0.25, 0.25)
        fill = await workflow.execute_activity(
            execute_trade, size, start_to_close_timeout=timedelta(seconds=10)
        )
        return {"action": "trade", "size": size, "fill": fill}


@workflow.defn
class GateWithoutCommand:
    @workflow.run
    async def run(self, order: Order) -> dict:
        fair = await workflow.execute_activity(
            analyst, order.market_price, start_to_close_timeout=timedelta(seconds=10)
        )
        edge = _net_edge(fair, order.market_price)
        if abs(edge) < cfg.MIN_EDGE_THRESHOLD:
            DECIDED.append("skip")
            return {"action": "skip", "size": 0.0}
        DECIDED.append("trade")
        size = order.equity * min(abs(edge) / 0.03 * 0.25, 0.25)
        return {"action": "trade", "size": size}


async def record(env: WorkflowEnvironment, wf, name: str, threshold: float):
    """Run the workflow once under `threshold` and return (result, history)."""
    cfg.MIN_EDGE_THRESHOLD = threshold
    client: Client = env.client
    async with Worker(
        client,
        task_queue="probe",
        workflows=[wf],
        activities=[analyst, execute_trade],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await client.start_workflow(
            wf.run,
            Order(market_price=3000.0, equity=5000.0),
            id=name,
            task_queue="probe",
        )
        result = await handle.result()
    history = await client.get_workflow_handle(name).fetch_history()
    return result, history


async def replay(wf, history, threshold: float):
    """Replay a recorded history with the threshold changed underneath it."""
    cfg.MIN_EDGE_THRESHOLD = threshold
    DECIDED.clear()
    try:
        await Replayer(
            workflows=[wf], workflow_runner=UnsandboxedWorkflowRunner()
        ).replay_workflow(history)
        return "REPLAY SUCCEEDED — no nondeterminism reported"
    except Exception as exc:  # noqa: BLE001 - the exception type is the finding
        return f"{type(exc).__name__}: {str(exc)[:140]}"


def decided_during_replay() -> str:
    return DECIDED[-1] if DECIDED else "(never reached the branch)"


def history_scan(history) -> dict:
    raw = json.dumps(history.to_json_dict())
    terms = ["0.0025", "0.0015", "MIN_EDGE_THRESHOLD", "threshold", "net_edge", "0.002"]
    return {"bytes": len(raw), "counts": {t: raw.count(t) for t in terms}}


async def main():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        print("=" * 78)
        print("A. The branch schedules an activity — the decision crosses a command boundary")
        print("=" * 78)
        result_a, history_a = await record(env, GateWithCommand, "wf-a", 0.0015)
        print(f"  recorded under threshold 0.0015 -> {result_a}")
        outcome_a = await replay(GateWithCommand, history_a, 0.0025)
        replay_decided_a = decided_during_replay()
        print(f"  replayed under threshold 0.0025 -> {outcome_a}")
        print(f"    the replayed code decided: {replay_decided_a}\n")

        print("=" * 78)
        print("B. The branch only changes the returned value — no command boundary")
        print("=" * 78)
        result_b, history_b = await record(env, GateWithoutCommand, "wf-b", 0.0015)
        print(f"  recorded under threshold 0.0015 -> {result_b}")
        outcome_b = await replay(GateWithoutCommand, history_b, 0.0025)
        replay_decided_b = decided_during_replay()
        print(f"  replayed under threshold 0.0025 -> {outcome_b}")
        print(f"    the replayed code decided: {replay_decided_b}")
        print(f"    the history says:          {result_b['action']}\n")

        print("=" * 78)
        print("What the history contains")
        print("=" * 78)
        for label, history in (("A", history_a), ("B", history_b)):
            scan = history_scan(history)
            print(f"  {label}: {scan['bytes']} bytes of history JSON")
            for term, count in scan["counts"].items():
                print(f"       {term:22} {count}")

        out = {
            "A": {"result": result_a, "replay": outcome_a,
                  "replay_decided": replay_decided_a, "scan": history_scan(history_a)},
            "B": {"result": result_b, "replay": outcome_b,
                  "replay_decided": replay_decided_b, "scan": history_scan(history_b)},
        }
        with open("findings.json", "w") as fh:
            json.dump(out, fh, indent=2)
        with open("history-a.json", "w") as fh:
            json.dump(history_a.to_json_dict(), fh, indent=2)
        with open("history-b.json", "w") as fh:
            json.dump(history_b.to_json_dict(), fh, indent=2)
        print("\nwrote findings.json, history-a.json, history-b.json")


if __name__ == "__main__":
    asyncio.run(main())
