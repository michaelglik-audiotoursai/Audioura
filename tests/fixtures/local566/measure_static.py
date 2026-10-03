import json, glob, os, collections, sys
sys.path.insert(0,"/Users/micha/audioura-worktrees/LOCAL-566")
REC = "/tmp/local566/local560/tests/fixtures/local560/recordings"
WRITER = "generate_tour_text.py:14129"
# gather all writer user messages, split into lines
allcalls=[]
for f in sorted(glob.glob(os.path.join(REC,"*.jsonl"))):
    slug=os.path.basename(f).replace(".jsonl","")
    with open(f) as fh:
        for line in fh:
            r=json.loads(line)
            if (r.get("site") or r.get("caller"))==WRITER:
                usr=next((m["content"] for m in r["messages"] if m["role"]=="user"),"")
                allcalls.append((slug,usr))
print(f"{len(allcalls)} writer calls total")

# Count line frequency across all calls: lines that appear in MANY calls are static boilerplate
line_freq=collections.Counter()
for slug,usr in allcalls:
    for ln in set(usr.split("\n")):
        line_freq[ln]+=1
N=len(allcalls)
# "static" = appears in >=90% of calls and non-trivial
static_lines=[ln for ln,c in line_freq.items() if c>=0.9*N and len(ln.strip())>3]
static_chars=sum(len(ln)+1 for ln in static_lines)
print(f"Lines appearing in >=90% of calls (static boilerplate): {len(static_lines)} lines, ~{static_chars} chars (~{static_chars//4} tokens)")

# For each call, how many chars are static-boilerplate vs variable, and WHERE does the first variable line appear
import statistics
avg_len=statistics.mean(len(u) for _,u in allcalls)
print(f"avg user msg len: {avg_len:.0f} chars (~{avg_len/4:.0f} tok)")
staticset=set(static_lines)
# position of static block: find index of first static line and whether a big contiguous static block exists
# Measure: in each call, chars BEFORE the first long static rule line (variable prefix that blocks caching)
def first_static_idx(lines):
    for i,ln in enumerate(lines):
        if ln in staticset and len(ln.strip())>30:
            return i
    return None
prefix_chars=[]
for slug,usr in allcalls:
    lines=usr.split("\n")
    i=first_static_idx(lines)
    if i is not None:
        prefix_chars.append(sum(len(l)+1 for l in lines[:i]))
print(f"\nVariable content SITTING BEFORE the big static rules block:")
print(f"  mean {statistics.mean(prefix_chars):.0f} chars (~{statistics.mean(prefix_chars)/4:.0f} tok), max {max(prefix_chars)} chars")
print(f"  => this variable prefix currently PREVENTS the static rules block from being cached")

# What's the biggest single component? classify static lines by prefix
print("\nLargest static boilerplate sections (sampled):")
# cluster by rough heading
blocks=collections.Counter()
for ln in static_lines:
    key = ln.strip()[:40]
    blocks[key]+=len(ln)
for k,v in blocks.most_common(15):
    print(f"  {v:>5} chars  {k!r}")
