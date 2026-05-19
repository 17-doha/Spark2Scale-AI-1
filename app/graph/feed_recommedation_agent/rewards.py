"""
Rewards Configuration
=====================
Defines interaction types and their associated RL reward hyperparameters.

Open/Closed Principle:
  - Adding a new interaction type = add an enum member + a REWARD_MATRIX entry.
  - No existing code needs modification.

Liskov Substitution:
  - ``InteractionType.from_payload()`` centralises the dispatch logic
    instead of duplicating fragile if/elif chains in route handlers.
"""

from enum import Enum
from pydantic import BaseModel


class InteractionType(str, Enum):
    CONTACT = "contact_founder"
    LIKE = "like"
    DISLIKE = "dislike"

    @classmethod
    def from_payload(cls, liked: bool, contacted: bool) -> tuple["InteractionType", str]:
        """
        Resolve the interaction type from payload boolean flags.

        Centralises the priority logic (contacted > liked > dislike)
        so route handlers don't duplicate fragile if/elif chains.

        Returns:
            (InteractionType, human-readable interaction string)
        """
        if contacted:
            return cls.CONTACT, "contact"
        elif liked:
            return cls.LIKE, "like"
        else:
            return cls.DISLIKE, "dislike"


class RewardConfig(BaseModel):
    reward: float
    alpha: float
    vector_beta: float


# The Hyperparameter Matrix
REWARD_MATRIX = {
    # Target is 1.0. Alpha is 0.3 (Fast learning).
    # Hit 1: 0.5 + 0.3*(1.0-0.5) = 0.65
    # Hit 2: 0.65 + 0.3*(1.0-0.65) = 0.755
    # Hit 3: 0.755 + 0.3*(1.0-0.755) = 0.828
    InteractionType.CONTACT: RewardConfig(reward=1.0, alpha=0.30, vector_beta=0.15),

    # Target is 0.8. Alpha is 0.15 (Slower learning).
    # Moves the weight up, but won't ever push it past 0.8.
    InteractionType.LIKE: RewardConfig(reward=0.8, alpha=0.15, vector_beta=0.05),

    # Target is 0.0 (punishing). Alpha is 0.20.
    InteractionType.DISLIKE: RewardConfig(reward=0.0, alpha=0.20, vector_beta=0.02),
}