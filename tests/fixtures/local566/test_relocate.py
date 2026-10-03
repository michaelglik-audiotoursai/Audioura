import os,sys,importlib
sys.path.insert(0,"/Users/micha/audioura-worktrees/LOCAL-566")
# import only the helpers without running the whole module side effects? module imports are heavy.
# We import the module (it may print), then test the pure functions.
import io,contextlib
buf=io.StringIO()
with contextlib.redirect_stdout(buf):
    import generate_tour_text as gtt

MUSEUM_BLOCK = gtt._WRITER_RELOCATABLE_BLOCKS[0]
GENERIC_BLOCK = gtt._WRITER_RELOCATABLE_BLOCKS[1]

# a realistic prompt: variable head + museum block + tail
sample = ("STYLE: curator voice\n\nCreate a detailed audio description for Harpe by Naderman at Palais Lascaris.\n\n"
          "IMPORTANT: already inside...\n\n" + MUSEUM_BLOCK + "\nNO CONDESCENSION:\n- more rules\n")

def approx_tok(s): return len(s)//4

# (a) flag off -> original
os.environ["WRITER_CACHE_PREFIX"]="0"
m0=gtt.build_writer_messages(sample)
assert m0[0]["content"]==gtt._WRITER_SYSTEM_BASE, "flag-off system changed"
assert m0[1]["content"]==sample, "flag-off user changed"
print("(a) flag OFF: original messages byte-for-byte  OK")

# (b) flag on -> exact relocation, same total instruction text
os.environ["WRITER_CACHE_PREFIX"]="1"
m1=gtt.build_writer_messages(sample)
# total text (system minus base + user) must equal original user text set
# reconstruct: user had block; now system has base+block, user lost block
assert MUSEUM_BLOCK not in m1[1]["content"], "block still in user"
assert MUSEUM_BLOCK.rstrip("\n") in m1[0]["content"], "block not in system"
# the multiset of lines is preserved (no instruction added/removed except role move)
orig_lines=sorted((gtt._WRITER_SYSTEM_BASE+"\n"+sample).split("\n"))
new_lines=sorted((m1[0]["content"]+"\n"+m1[1]["content"]).split("\n"))
assert orig_lines==new_lines, "LINE SET CHANGED! not a pure relocation"
print(f"(b) flag ON: pure relocation, line-set identical. system tokens ~{approx_tok(m1[0]['content'])}  OK")

# (c) unknown prompt -> no-op
unknown="STYLE: x\n\nCreate ... no known block here\n"
m2=gtt.build_writer_messages(unknown)
assert m2[0]["content"]==gtt._WRITER_SYSTEM_BASE and m2[1]["content"]==unknown, "unknown not no-op"
print("(c) unknown template: no-op  OK")

# generic block variant
sample_g=("STYLE: y\n\nCreate a detailed description for the stop...\n\n"+GENERIC_BLOCK+"\nNO CONDESCENSION:\n- x\n")
m3=gtt.build_writer_messages(sample_g)
assert GENERIC_BLOCK not in m3[1]["content"] and GENERIC_BLOCK.rstrip("\n") in m3[0]["content"]
og=sorted((gtt._WRITER_SYSTEM_BASE+"\n"+sample_g).split("\n")); ng=sorted((m3[0]["content"]+"\n"+m3[1]["content"]).split("\n"))
assert og==ng
print("(d) generic block relocation: line-set identical  OK")
print("\nALL RELOCATION TESTS PASSED")
