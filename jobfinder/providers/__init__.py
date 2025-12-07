from .greenhouse import GreenhouseProvider
from .lever import LeverProvider
PROVIDERS = {"greenhouse": GreenhouseProvider(), "lever": LeverProvider()}
__all__ = ["PROVIDERS"]
