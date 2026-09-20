"""Backward-compatible import; new code should use paper_agent.agent_team."""

from paper_agent.agent_team import AgentResearchTeam

OpenAIResearchTeam = AgentResearchTeam

__all__ = ["OpenAIResearchTeam"]

