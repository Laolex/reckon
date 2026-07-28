package trading.gate

import rego.v1

# A two-gate position-sizing policy of the kind an autonomous trading agent runs.
# Gate A: abs(net_edge) < min_edge_threshold -> skip   [equity-independent]
# Gate B: size_usd < min_order_size_usd      -> skip   [equity-dependent]
# Both thresholds are read from data.config, which is what puts them outside the
# bundle's declared roots and therefore outside the record. That is the point.

default decision := {"action": "skip", "gate": "unknown"}

net_edge := input.raw_edge - (input.funding_rate_hourly * input.hours_to_close)

kelly_scaled := m if {
	raw := abs(net_edge) / input.stop_loss_pct
	decayed := raw * max([0.1, 1.0 - (input.hours_to_close / 72)])
	m := min([decayed * data.config.kelly_fraction, data.config.max_kelly_fraction])
}

size_usd := kelly_scaled * input.account_equity

decision := {"action": "skip", "gate": "A", "reason": "edge below threshold"} if {
	abs(net_edge) < data.config.min_edge_threshold
}

decision := {"action": "skip", "gate": "B", "reason": "size below floor"} if {
	abs(net_edge) >= data.config.min_edge_threshold
	size_usd < data.config.min_order_size_usd
}

decision := {"action": "trade", "gate": "pass", "size_usd": size_usd} if {
	abs(net_edge) >= data.config.min_edge_threshold
	size_usd >= data.config.min_order_size_usd
}
