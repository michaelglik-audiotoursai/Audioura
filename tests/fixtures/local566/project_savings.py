import json,glob,os,sys
sys.path.insert(0,"/Users/micha/audioura-worktrees/LOCAL-566")
from cost_rates import llm_cost
REC="/tmp/local566/local560/tests/fixtures/local560/recordings"
WRITER="generate_tour_text.py:14129"
IN_RATE=2.50/1e6
calls=[]
for f in sorted(glob.glob(os.path.join(REC,"*.jsonl"))):
    with open(f) as fh:
        for line in fh:
            r=json.loads(line)
            if (r.get("site") or r.get("caller"))==WRITER:
                u=r.get("usage") or {}
                calls.append((u.get("prompt_tokens",0),(u.get("prompt_tokens_details") or {}).get("cached_tokens",0)))
tot_in=sum(p for p,_ in calls)
tot_cached=sum(c for _,c in calls)
uncached=tot_in-tot_cached
# OpenAI cached input is billed at 50% for gpt-4o. Full input cost already reflects this ONLY if the recorder's cost used split... but our llm_cost does NOT discount cached. 
# cost_rates.llm_cost bills ALL input at full rate (no cache discount). So our $1.777 input cost is the UNDISCOUNTED figure.
# Real OpenAI bill with 50% cache discount on cached tokens:
billed_full = tot_in*IN_RATE
billed_with_cache = (uncached + tot_cached*0.5)*IN_RATE
print(f"Writer input tokens total: {tot_in:,}")
print(f"  cached: {tot_cached:,} ({100*tot_cached/tot_in:.1f}%)   uncached: {uncached:,}")
print(f"Input $ (no cache discount, as cost_rates computes): ${billed_full:.4f}")
print(f"Input $ (with OpenAI 50% cached discount applied):     ${billed_with_cache:.4f}  (saves ${billed_full-billed_with_cache:.4f} already)")
print()
# Reordering upside: the ~158-tok variable prefix (mean) blocks the static ~2203-tok block from the cached prefix on WARM calls,
# and all content on COLD calls. Estimate incremental cacheable tokens.
# Conservative model: on each warm call, moving static-first lets ~2203 more tokens join the cached prefix (they already repeat).
# Count warm calls (cached>0):
warm=[(p,c) for p,c in calls if c>0]
cold=[(p,c) for p,c in calls if c==0]
print(f"warm calls (cached>0): {len(warm)}   cold calls (cached==0): {len(cold)}")
# On warm calls, extra tokens that could shift from uncached->cached, bounded by current uncached on that call and ~2203
extra_warm=sum(min(p-c, 2203) for p,c in warm)
# discount benefit = those tokens move from full to 50%
save_warm = extra_warm*0.5*IN_RATE
print(f"Warm-call reorder upside: up to {extra_warm:,} tok shift to cached -> save ~${save_warm:.4f}")
# cold calls: 2nd+ cold calls could become warm if a stable >=1024 prefix exists from call #1. Hard to model offline; note qualitatively.
print(f"Cold calls remain cold on first occurrence regardless; reorder mainly helps calls 2+.")
print()
print(f"NET: current OpenAI-billed writer input ~${billed_with_cache:.3f}; reorder could save roughly ${save_warm:.3f} more on these 8 tours (~{100*save_warm/billed_with_cache:.0f}% of input bill). Small but safe & free.")
