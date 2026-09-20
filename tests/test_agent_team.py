from paper_agent.agent_team import _normalize_citations


def test_citations_are_normalized_and_filtered_against_context() -> None:
    allowed = {"paper:p1:c0", "paper:p2:c0"}

    citations = _normalize_citations(
        [
            "paper:p1:c0",
            '{"chunk_id": "paper:p2:c0", "page": 2}',
            "paper:p1:c0",
            "invented:p9:c9",
        ],
        allowed,
    )

    assert citations == ["paper:p1:c0", "paper:p2:c0"]
