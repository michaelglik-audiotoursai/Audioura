"""
Onboarding Preference — user persona definitions and story-type weighting.
===========================================================================
Pure logic, no DB, stdlib only. Maps user personas to story-type preferences
for personalizing tour narration style.
"""
from enum import Enum
from typing import Dict


class UserPersona(Enum):
    ART_LOVER = "art_lover"
    HISTORY_BUFF = "history_buff"
    FAMILY = "family"
    FIRST_TIME_VISITOR = "first_time_visitor"


# Story type keys (must match story_type_taxonomy.json)
_STORY_TYPES = ("history", "anecdote", "architecture", "culture", "nature", "art")


def persona_to_story_type_weights(persona: UserPersona) -> Dict[str, float]:
    """Return story-type weights for a persona. All weights sum to 1.0.

    Higher weight = that story type is preferred for this persona.
    All 6 story types are present in every persona's weights.
    """
    weights = {
        UserPersona.ART_LOVER: {
            "history": 0.05,
            "anecdote": 0.15,
            "architecture": 0.10,
            "culture": 0.10,
            "nature": 0.10,
            "art": 0.50,
        },
        UserPersona.HISTORY_BUFF: {
            "history": 0.45,
            "anecdote": 0.15,
            "architecture": 0.20,
            "culture": 0.10,
            "nature": 0.05,
            "art": 0.05,
        },
        UserPersona.FAMILY: {
            "history": 0.10,
            "anecdote": 0.35,
            "architecture": 0.05,
            "culture": 0.20,
            "nature": 0.20,
            "art": 0.10,
        },
        UserPersona.FIRST_TIME_VISITOR: {
            "history": 0.20,
            "anecdote": 0.25,
            "architecture": 0.15,
            "culture": 0.20,
            "nature": 0.10,
            "art": 0.10,
        },
    }
    return weights[persona]


# Persona → tone adjective (modifies the overall narration voice)
PERSONA_TONE_OVERRIDE: Dict[UserPersona, str] = {
    UserPersona.ART_LOVER: "passionate and visually evocative",
    UserPersona.HISTORY_BUFF: "authoritative and richly detailed",
    UserPersona.FAMILY: "warm, playful, and engaging for all ages",
    UserPersona.FIRST_TIME_VISITOR: "welcoming, clear, and gently guiding",
}
