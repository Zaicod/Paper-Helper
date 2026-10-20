"""Server-scoped live evidence dependencies; demo storage stays explicitly offline."""
import os
from pathlib import Path


def build_paper_index(options):
    from paper_agent.tools.chroma_index import ChromaVectorIndex
    if options.embedding_provider == 'qwen':
        from paper_agent.services.research import ResearchConfigurationError
        from paper_agent.agents.providers import (
            DEFAULT_QWEN_BASE_URL, DEFAULT_QWEN_EMBEDDING_MODEL, build_qwen_client,
        )
        from paper_agent.tools.rag import OpenAICompatibleEmbedder
        key = os.getenv('DASHSCOPE_API_KEY', '').strip()
        if not key:
            raise ResearchConfigurationError('Qwen Embedding 需要 DASHSCOPE_API_KEY。')
        embedder = OpenAICompatibleEmbedder(
            build_qwen_client(key, os.getenv('DASHSCOPE_BASE_URL', DEFAULT_QWEN_BASE_URL)),
            options.embedding_model or os.getenv('QWEN_EMBEDDING_MODEL', DEFAULT_QWEN_EMBEDDING_MODEL),
            dimensions=1024,
        )
    else:
        from paper_agent.tools.local_embeddings import LocalMultilingualEmbedder
        embedder = LocalMultilingualEmbedder()
    return ChromaVectorIndex(embedder,
        path=Path(os.getenv('PAPERFLOW_CHROMA_DIR', 'outputs/chroma')),
        namespace=options.index_namespace, embedding_id=embedder.embedding_id,
        dimensions=embedder.dimensions)
