"""Verify real local E5 + real Chroma retrieval across independent processes.

No hosted model, PDF download, or generation-model API is involved. The short
evidence passages are controlled fixtures; embedding and storage are real.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper_agent.core.models import EvidenceChunk, Paper
from paper_agent.tools.chroma_index import ChromaVectorIndex
from paper_agent.tools.local_embeddings import LocalMultilingualEmbedder


class CountingModel:
    def __init__(self, model):
        self.model = model
        self.document_count = 0

    async def embed(self, texts):
        self.document_count += len(texts)
        return await self.model.embed(texts)

    async def embed_query(self, texts):
        return await self.model.embed_query(texts)


def _paper(identifier='fusion'):
    return Paper(paper_id=identifier, source='controlled-smoke', title='Controlled ' + identifier,
                 authors=['Fixture'], abstract='Controlled multilingual evidence.',
                 page_url='https://example.org/' + identifier,
                 pdf_url='https://example.org/' + identifier + '.pdf')


def _chunks(identifier='fusion'):
    return [EvidenceChunk(chunk_id=f'{identifier}:p{index}:c0', paper_id=identifier,
                          text=text, page_number=index, source_url=_paper(identifier).pdf_url)
            for index, text in enumerate([
                'A multimodal model combines visual image features and natural language text representations using a cross-attention fusion module.',
                'Bread is baked in an oven using flour, yeast, water, and salt.',
                'Database transactions ensure consistency and isolation when updating customer records.',
            ], start=1)]


async def stage(args):
    model = LocalMultilingualEmbedder(model_dir=args.model_dir)
    counted = CountingModel(model)
    def index(namespace='smoke:owner'):
        return ChromaVectorIndex(counted, path=args.database, namespace=namespace,
                                 embedding_id=model.embedding_id, dimensions=model.dimensions)
    if args.stage == 'write':
        writer = index()
        await writer.replace_paper(_paper(), _chunks(), 'pdf', 'smoke-v1')
        await writer.replace_paper(_paper('unselected'), _chunks('unselected'), 'pdf', 'smoke-v1')
        return {'documents_embedded': counted.document_count, 'embedding_id': model.embedding_id,
                'dimensions': model.dimensions, 'chunk_count': writer._chunks.count()}
    reader = index()
    assert await reader.load_paper(_paper(), 'pdf', 'smoke-v1')
    assert not await index('smoke:other-owner').load_paper(_paper(), 'pdf', 'smoke-v1')
    assert await reader.search('fusion', paper_id='unselected') == []
    results = []
    for query in ('How does the model combine images and language?', '模型如何融合图像和文本特征？'):
        retrieved = await reader.search(query, top_k=3)
        assert retrieved and retrieved[0].chunk_id == 'fusion:p1:c0', retrieved
        assert all(chunk.paper_id == 'fusion' for chunk in retrieved)
        assert retrieved[0].page_number == 1
        results.append({'query': query, 'best_chunk': retrieved[0].chunk_id,
                        'scores': [chunk.score for chunk in retrieved]})
    assert counted.document_count == 0
    return {'reopened_after_process_exit': True, 'cached_document_embeddings': counted.document_count,
            'account_isolation': True, 'selected_paper_isolation': True,
            'original_citation_and_page': True, 'queries': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=ROOT / 'outputs/models/multilingual-e5-small')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / '.tools/chroma-live-smoke.json')
    parser.add_argument('--stage', choices=('write', 'read'))
    args = parser.parse_args()
    if args.stage:
        print(json.dumps(asyncio.run(stage(args)), ensure_ascii=True))
        return
    database = args.database or ROOT / '.tools/chroma-smoke' / uuid.uuid4().hex
    stages = {}
    for name in ('write', 'read'):
        process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                                  '--stage', name, '--database', str(database),
                                  '--model-dir', str(args.model_dir)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=180)
        if process.returncode:
            raise RuntimeError(f'Chroma {name} verification failed: {process.stderr[-4000:]}')
        stages[name] = json.loads(process.stdout.strip().splitlines()[-1])
    result = {'verified': True, 'real_local_multilingual_model': True, 'real_chroma': True,
              'controlled_evidence_text': True, 'generation_model_verified': False,
              'database': str(database), **stages}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Real multilingual Chroma cross-process verification passed: {args.output}')


if __name__ == '__main__':
    main()
