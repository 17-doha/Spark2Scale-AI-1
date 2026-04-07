from enum import Enum
from pydantic import BaseModel

class InteractionType(str, Enum):
    CONTACT = "contact_founder"
    LIKE = "like"
    DISLIKE = "dislike"
    SKIP = "skip"

class RewardConfig(BaseModel):
    reward: float
    alpha: float
    vector_beta: float

# The Hyperparameter Matrix
REWARD_MATRIX = {
    InteractionType.CONTACT: RewardConfig(reward=10.0, alpha=0.30, vector_beta=0.15),
    InteractionType.LIKE: RewardConfig(reward=1.0, alpha=0.10, vector_beta=0.05),
    InteractionType.DISLIKE: RewardConfig(reward=-1.0, alpha=0.05, vector_beta=0.02),
    InteractionType.SKIP: RewardConfig(reward=-0.1, alpha=0.01, vector_beta=0.00),
}