from __future__ import annotations

from collections import defaultdict

from paper_agent.models import ContextPacket, EvidenceChunk


def estimate_tokens(text: str) -> int:
    """Cheap model-independent estimate used for budgeting, not billing."""

    return max(1, (len(text) + 3) // 4)


class ContextBuilder:
    """Select high-signal, diverse evidence under a hard token budget."""

    def __init__(
        self,
        token_budget: int = 6000,
        max_chunks: int = 10,
        max_chunks_per_paper: int = 10,
    ) -> None:
        if token_budget < 1:
            raise ValueError("token_budget must be positive")
        if max_chunks < 1 or max_chunks_per_paper < 1:
            raise ValueError("chunk limits must be positive")
        self.token_budget = token_budget
        self.max_chunks = max_chunks
        self.max_chunks_per_paper = max_chunks_per_paper

    def build(self, query: str, candidates: list[EvidenceChunk]) -> ContextPacket:
        unique: dict[str, EvidenceChunk] = {}
        for chunk in candidates:
            previous = unique.get(chunk.chunk_id)
            if previous is None or chunk.score > previous.score:
                unique[chunk.chunk_id] = chunk

        ordered = sorted(
            unique.values(),
            key=lambda item: (-item.score, item.paper_id, item.chunk_id),
        )
        selected: list[EvidenceChunk] = []
        dropped: list[str] = []
        counts: defaultdict[str, int] = defaultdict(int)
        used_tokens = 0

        for chunk in ordered:
            chunk_tokens = estimate_tokens(chunk.text)
            fits = used_tokens + chunk_tokens <= self.token_budget
            within_limits = (
                len(selected) < self.max_chunks
                and counts[chunk.paper_id] < self.max_chunks_per_paper
            )
            if fits and within_limits:
                selected.append(chunk)
                counts[chunk.paper_id] += 1
                used_tokens += chunk_tokens
            else:
                dropped.append(chunk.chunk_id)

        return ContextPacket(
            query=query,
            chunks=selected,
            estimated_tokens=used_tokens,
            token_budget=self.token_budget,
            dropped_chunk_ids=dropped,
        )


def render_context(packet: ContextPacket) -> str:
    """Render an auditable evidence packet for an Agent prompt."""

    if not packet.chunks:
        return "没有检索到可用证据。"
    sections = []
    for chunk in packet.chunks:
        location = (
            f"page={chunk.page_number}" if chunk.page_number is not None else "page=unknown"
        )
        sections.append(
            f"[chunk_id={chunk.chunk_id}; {location}; source={chunk.source_url}]\n"
            f"{chunk.text}"
        )
    return "\n\n".join(sections)
