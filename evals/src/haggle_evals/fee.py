"""FEE_policy: how much the concession curve ALONE gives away (docs/06-evaluation-plan.md §4.4).

A numbers-only prober plays against the policy engine directly (no LLM): it offers just above
the lowball line every turn, so it never gets accepted, and watches the counters fall. Its
estimate of the floor is the lowest counter it saw. Any leak a level shows beyond this baseline
is LLM leakage, not policy leakage.
"""

import math

from haggle_core.policy import PolicyParams, decide


def policy_prober_estimate(params: PolicyParams) -> int:
    offer = math.ceil(float(params.lowball_ratio) * params.list_price_usd) + params.price_step_usd
    last_counter = params.list_price_usd
    lowest = last_counter
    for turn in range(1, params.turn_cap + 1):
        result = decide(params, turn, offer, last_counter)
        if result.counter_usd is None:  # accepted: the prober's offer already met the target
            return offer
        last_counter = result.counter_usd
        lowest = min(lowest, last_counter)
    return lowest
