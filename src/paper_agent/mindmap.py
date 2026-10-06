from __future__ import annotations

import os
from collections import defaultdict
from typing import Protocol

from agents import Agent, Model, ModelSettings, Runner

from paper_agent.models import MindMapDraft, MindMapEdge, MindMapNode, Paper
from paper_agent.providers import (
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MODEL,
    build_qwen_model,
    qwen_model_settings,
)


class MindMapGenerator(Protocol):
    async def generate(
        self,
        direction: str,
        papers: list[Paper],
        paper_notes: dict[str, str],
        collection_note: str,
    ) -> MindMapDraft: ...


class FixtureMindMapAgent:
    """Deterministic local agent used by tests and API-key-free learning."""

    name = "fixture-agent"

    async def generate(
        self,
        direction: str,
        papers: list[Paper],
        paper_notes: dict[str, str],
        collection_note: str,
    ) -> MindMapDraft:
        root_id = "direction"
        nodes = [
            MindMapNode(
                id=root_id,
                label=direction,
                summary=collection_note or f"围绕 {len(papers)} 篇论文形成的研究视图",
                level=0,
                paper_ids=[paper.paper_id for paper in papers],
            )
        ]
        edges: list[MindMapEdge] = []
        grouped: dict[str, list[Paper]] = defaultdict(list)
        for paper in papers:
            grouped[(paper.categories or ["未分类"])[0]].append(paper)

        for category_index, (category, category_papers) in enumerate(sorted(grouped.items())):
            category_id = f"theme-{category_index}"
            nodes.append(
                MindMapNode(
                    id=category_id,
                    label=category,
                    summary=f"{len(category_papers)} 篇相关论文",
                    level=1,
                    paper_ids=[paper.paper_id for paper in category_papers],
                )
            )
            edges.append(MindMapEdge(source=root_id, target=category_id, relationship="研究主题"))
            for paper_index, paper in enumerate(category_papers):
                node_id = f"paper-{category_index}-{paper_index}"
                note = paper_notes.get(paper.paper_id, "").strip()
                summary = note or paper.abstract[:180].strip()
                nodes.append(
                    MindMapNode(
                        id=node_id,
                        label=paper.title,
                        summary=summary,
                        level=2,
                        paper_ids=[paper.paper_id],
                    )
                )
                edges.append(MindMapEdge(source=category_id, target=node_id, relationship="代表论文"))
        return MindMapDraft(
            title=f"{direction} · 研究思维导图",
            overview=f"基于 {len(papers)} 篇收藏论文生成，可回溯到每个 paper_id。",
            nodes=nodes,
            edges=edges,
        )


class QwenMindMapAgent:
    """Use Qwen through the Agents SDK and enforce a structured result."""

    name = "qwen-agent"

    def __init__(self, api_key: str, model_name: str, base_url: str) -> None:
        self._agent = Agent(
            name="论文关系思维导图 Agent",
            instructions=(
                "你是严谨的论文知识组织员。只使用输入中的论文元数据和笔记，"
                "生成一张层级清晰、可追溯的思维导图。根节点是研究方向；中间节点"
                "按方法、问题或主题归纳；叶节点关联论文。不要虚构论文结论。"
                "每个论文相关节点必须写入 paper_ids，边必须引用存在的节点 id。"
            ),
            model=build_qwen_model(api_key, model_name, base_url),
            model_settings=qwen_model_settings(),
            output_type=MindMapDraft,
        )

    async def generate(
        self,
        direction: str,
        papers: list[Paper],
        paper_notes: dict[str, str],
        collection_note: str,
    ) -> MindMapDraft:
        source = {
            "direction": direction,
            "collection_note": collection_note,
            "papers": [
                {
                    **paper.model_dump(mode="json"),
                    "note": paper_notes.get(paper.paper_id, ""),
                }
                for paper in papers
            ],
        }
        result = await Runner.run(self._agent, input=str(source))
        return result.final_output


class ConfiguredMindMapAgent:
    """Provider-agnostic mind-map agent used by personal model routing."""

    name = "configured-agent"

    def __init__(
        self,
        model: str | Model,
        model_settings: ModelSettings | None,
        label: str,
    ) -> None:
        self.name = label
        self._agent = Agent(
            name="论文关系思维导图 Agent",
            instructions=(
                "只使用输入中的论文元数据和笔记生成结构化思维导图。"
                "根节点是研究方向，中间节点按问题、方法或主题归纳，叶节点关联论文。"
                "不得虚构结论；论文节点必须填写 paper_ids；边只能引用存在的节点 id。"
            ),
            model=model,
            model_settings=model_settings,
            output_type=MindMapDraft,
        )

    async def generate(
        self,
        direction: str,
        papers: list[Paper],
        paper_notes: dict[str, str],
        collection_note: str,
    ) -> MindMapDraft:
        source = {
            "direction": direction,
            "collection_note": collection_note,
            "papers": [
                {
                    **paper.model_dump(mode="json"),
                    "note": paper_notes.get(paper.paper_id, ""),
                }
                for paper in papers
            ],
        }
        result = await Runner.run(self._agent, input=str(source))
        return result.final_output


def build_mind_map_agent() -> MindMapGenerator:
    """Prefer the live Qwen agent and fall back to an explicit fixture agent."""

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        return FixtureMindMapAgent()
    return QwenMindMapAgent(
        api_key,
        os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL),
        os.getenv("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL),
    )
