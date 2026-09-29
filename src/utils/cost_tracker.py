"""
Tracks LLM token usage and estimated $ cost per pipeline run. Clients
consistently care about LLM spend, so surfacing "this article cost
$0.04 to generate" in the final package is a small feature with an
outsized trust payoff in a sales conversation.

Prices are per 1M tokens (input, output) in USD and are approximate —
update PRICING as models/providers change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}
DEFAULT_PRICING = {"input": 0.50, "output": 1.50}


@dataclass
class CallCost:
    node: str
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def usd(self) -> float:
        price = PRICING.get(self.model, DEFAULT_PRICING)
        return (
            self.input_tokens / 1_000_000 * price["input"]
            + self.output_tokens / 1_000_000 * price["output"]
        )


@dataclass
class CostTracker:
    calls: List[CallCost] = field(default_factory=list)

    def record(self, node: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.calls.append(CallCost(node, model, input_tokens, output_tokens))

    @property
    def total_usd(self) -> float:
        return round(sum(c.usd for c in self.calls), 5)

    @property
    def total_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.calls)

    def report(self) -> dict:
        return {
            "total_usd": self.total_usd,
            "total_tokens": self.total_tokens,
            "by_node": [
                {
                    "node": c.node,
                    "model": c.model,
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "usd": round(c.usd, 5),
                }
                for c in self.calls
            ],
        }
