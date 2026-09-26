from abc import ABC, abstractmethod

class VisionBackend(ABC):
    @abstractmethod
    def predict(self, image_a, image_b, metadata=None):
        raise NotImplementedError
