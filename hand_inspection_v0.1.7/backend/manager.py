from .openai_api import OpenAIBackend
from .custom_api import CustomAPIBackend
from .random_mock import RandomBackend
from .simulation_table import SimulationTableBackend

def create_backend(mode, settings):
    if mode == "OpenAI API":
        return OpenAIBackend(settings.get("token", ""), settings.get("model", "gpt-5.6-luna"), settings.get("uri", ""))
    if mode == "Custom API":
        return CustomAPIBackend(settings.get("uri", ""), settings.get("token", ""), settings.get("model", ""))
    if mode == "Random Mock":
        return RandomBackend()
    if mode == "Simulation Table":
        return SimulationTableBackend(settings.get("simulation_table", ""))
    raise ValueError(f"未知辨識模式：{mode}")
