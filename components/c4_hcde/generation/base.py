"""Single interface for tier-calibrated generation. Prompted model now, QLoRA adapter later."""
from shared.schemas import AssistanceTier


def generate(task: str, tier: AssistanceTier, history: list[dict] | None = None) -> str:
    raise NotImplementedError
