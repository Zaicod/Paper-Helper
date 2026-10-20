"""Prepare the pinned CPU model once, optionally verify multilingual retrieval."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_agent.tools.local_embeddings import LocalMultilingualEmbedder, prepare_model
from paper_agent.core.models import EvidenceChunk


async def smoke(folder: Path | None) -> dict:
    model = LocalMultilingualEmbedder(model_dir=folder)
    passages = [
        'A multimodal model combines visual image features and natural language text representations using a cross-attention fusion module.',
        'Bread is baked in an oven using flour, yeast, water, and salt.',
        'Database transactions ensure consistency and isolation when updating customer records.',
    ]
    vectors = await model.embed(passages)
    queries = ['How does the model combine images and language?', '模型如何融合图像和文本特征？']
    scores = []
    for query in queries:
        vector = (await model.embed_query([query]))[0]
        similarities = [sum(a*b for a, b in zip(vector, row)) for row in vectors]
        if max(range(len(similarities)), key=similarities.__getitem__) != 0:
            raise RuntimeError('Multilingual semantic retrieval smoke failed')
        scores.append({'query': query, 'similarities': similarities, 'best_passage': 0})
    long_text = '模型融合图像和文本特征，使用交叉注意力模块。' * 100 + ' TAIL-EVIDENCE'
    chunks = await model.split_chunks([EvidenceChunk(
        chunk_id='smoke:p3:c0', paper_id='smoke', text=long_text,
        source_url='https://example.org/paper.pdf', page_number=3,
    )])
    assert ''.join(chunk.text for chunk in chunks) == long_text
    runtime = model._runtime()
    with runtime.lock:
        runtime.tokenizer.no_truncation()
        try:
            token_counts = [len(runtime.tokenizer.encode('passage: ' + chunk.text).ids) for chunk in chunks]
        finally:
            runtime.tokenizer.enable_truncation(max_length=512)
    assert max(token_counts) <= 500 and len(chunks) > 1
    return {'verified': True, 'embedding_id': model.embedding_id, 'dimensions': model.dimensions, 'cpu_only': True, 'queries': scores,
            'long_passage': {'all_characters_preserved': True, 'chunks': len(chunks), 'token_counts': token_counts, 'page_number': 3}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Optional explicit model folder; defaults to the Hugging Face cache used by the application.')
    parser.add_argument('--smoke-json', type=Path)
    args = parser.parse_args()
    folder = prepare_model(args.output_dir.resolve() if args.output_dir else None)
    print(f'Model prepared: {folder}')
    if args.smoke_json:
        # Exercise the same constructor used by the application when no custom
        # directory was requested, including its pinned-cache loading path.
        result = asyncio.run(smoke(folder if args.output_dir else None))
        args.smoke_json.parent.mkdir(parents=True, exist_ok=True)
        args.smoke_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Multilingual retrieval verified: {args.smoke_json}')


if __name__ == '__main__':
    main()
