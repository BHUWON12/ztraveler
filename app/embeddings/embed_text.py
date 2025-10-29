import numpy as np

# TEMP stub until we integrate real OpenAI / HuggingFace embeddings
# Each call returns a deterministic small random vector for testing.
def embed_text(text: str) -> np.ndarray:
    if not text:
        text = "empty"
    np.random.seed(abs(hash(text)) % (2**32))  # deterministic for same text
    return np.random.rand(1536).astype(np.float32)
