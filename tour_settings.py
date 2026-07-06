# Walking-tour compactness thresholds (straight-line km).
# The PHASE 3A prompt aims at the TARGET; the geometric verifier only rejects
# above the HARD limit, so it catches gross hallucinations without fighting GPT
# over a legitimate borderline leg.
WALKING_LEG_TARGET_KM    = 1.0    # what the prompt asks GPT for
WALKING_LEG_HARD_KM      = 1.75   # verifier rejects a sequential leg above this
WALKING_TOTAL_HARD_KM    = 12.0   # backstop on total straight-line route length
SPECIALIZED_LEG_HARD_KM  = 4.0    # biking / driving / themed tours “Çö looser (future)
MAX_REPLACEMENT_ATTEMPTS = 2      # Part C replacement loop cap
