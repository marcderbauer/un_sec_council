from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
from sentence_transformers.quantization import quantize_embeddings

# 1. Specify preffered dimensions
dimensions = 512

# 2. load model
model = SentenceTransformer("mixedbread-ai/mxbai-embed-large-v1", truncate_dim=dimensions)


def get_embedding(text: str, use_case: str = "clustering", quantize: bool = True) -> str:
    prompt = f"Represent this sentence for {use_case}: {text}"
    embedding = model.encode(prompt)

    if quantize:
        return quantize_embeddings(embedding, precision="ubinary")

    return embedding

# * Only for reference, can probably remove
def get_similarity(embedding_1, embedding_2):
    return cos_sim(embedding_1, embedding_2)