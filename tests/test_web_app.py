from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from paper_agent.web_app import ResearchRequest, ResearchTaskManager, create_app
from paper_agent.mindmap import FixtureMindMapAgent
from paper_agent.auth import AuthenticationService, InMemorySessionStore
from paper_agent.model_settings import PersonalModelSettings
from paper_agent.storage import PaperLibrary


async def test_task_manager_streams_nodes_and_saves_artifacts(
    tmp_path: Path,
) -> None:
    manager = ResearchTaskManager(tmp_path)
    started = await manager.start(ResearchRequest(topic="RAG", limit=2))
    completed = await manager.wait(started.task_id)

    assert completed.status == "completed"
    assert len(completed.files) == 3
    assert all((tmp_path / started.task_id / name).is_file() for name in completed.files)

    subscription = await manager.subscribe(started.task_id)
    assert subscription is not None
    history, queue, terminal = subscription
    assert queue.empty()
    assert terminal is True
    assert [event.node for event in history if event.type == "node"] == [
        "search",
        "analyze",
        "synthesize",
        "ideate",
        "render",
    ]


async def test_web_api_starts_and_reports_research_task(tmp_path: Path) -> None:
    manager = ResearchTaskManager(tmp_path)
    app = create_app(manager=manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/research",
            json={"topic": "RAG", "limit": 1, "category": "cs.CL"},
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]

        await manager.wait(task_id)
        detail = await client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "completed"
        assert len(payload["artifacts"]) == 3

        artifact = await client.get(payload["artifacts"][0])
        assert artifact.status_code == 200
        assert "研究方向报告：RAG" in artifact.text


def test_artifact_path_cannot_escape_task_directory(tmp_path: Path) -> None:
    manager = ResearchTaskManager(tmp_path)

    assert manager.resolve_artifact("task", "../secret.txt") is None
    assert manager.resolve_artifact("task", "subdir/report.md") is None


def test_websocket_replays_graph_node_events(tmp_path: Path) -> None:
    manager = ResearchTaskManager(tmp_path)
    app = create_app(manager=manager)

    with TestClient(app) as client:
        response = client.post(
            "/api/research", json={"topic": "RAG", "limit": 1}
        )
        task_id = response.json()["task_id"]

        node_names = []
        with client.websocket_connect(f"/ws/{task_id}") as websocket:
            while True:
                event = websocket.receive_json()
                if event["type"] == "node":
                    node_names.append(event["node"])
                if event["type"] in {"completed", "error"}:
                    assert event["type"] == "completed"
                    break

    assert node_names == ["search", "analyze", "synthesize", "ideate", "render"]


def test_built_frontend_and_assets_are_served(tmp_path: Path) -> None:
    manager = ResearchTaskManager(tmp_path)
    app = create_app(manager=manager)

    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert '<div id="root"></div>' in index.text

        asset_path = index.text.split('src="')[1].split('"')[0]
        asset = client.get(asset_path)
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]

        for route in ("/library", "/tasks", "/collections"):
            routed_page = client.get(route)
            assert routed_page.status_code == 200
            assert '<div id="root"></div>' in routed_page.text


async def test_web_task_persists_papers_to_library(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    started = await manager.start(ResearchRequest(topic="RAG", limit=2))
    completed = await manager.wait(started.task_id)

    assert completed.status == "completed"
    assert completed.library_run_id == started.task_id
    assert len(library.list_papers()) == 2
    library.close()


async def test_library_api_manages_collection_and_tag(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    app = create_app(manager=manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        started = await client.post(
            "/api/research", json={"topic": "RAG", "limit": 1}
        )
        task_id = started.json()["task_id"]
        await manager.wait(task_id)

        papers = await client.get("/api/library/papers")
        assert papers.json()["papers"][0]["paper_id"] == "demo-001"

        collection = await client.post(
            "/api/library/collections",
            json={"name": "必读", "description": "面试复习"},
        )
        collection_id = collection.json()["id"]
        added = await client.post(
            f"/api/library/collections/{collection_id}/papers",
            json={"source": "demo", "paper_id": "demo-001"},
        )
        tagged = await client.post(
            "/api/library/papers/demo/demo-001/tags", json={"tag": "RAG"}
        )
        detail = await client.get("/api/library/papers/demo/demo-001")

        assert added.status_code == 204
        assert tagged.status_code == 204
        assert detail.json()["tags"] == ["RAG"]
        assert (await client.get("/api/library/collections")).json()[
            "collections"
        ][0]["paper_count"] == 1
        searched = await client.get("/api/library/collections?query=必读")
        deleted = await client.delete(
            f"/api/library/collections/{collection_id}"
        )
        paper_after_delete = await client.get(
            "/api/library/papers/demo/demo-001"
        )

        assert [item["name"] for item in searched.json()["collections"]] == ["必读"]
        assert deleted.status_code == 204
        assert paper_after_delete.status_code == 200
    library.close()


async def test_collection_research_notes_and_mind_map_api(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    seed = await manager.start(ResearchRequest(topic="RAG", limit=2))
    await manager.wait(seed.task_id)
    collection = library.create_collection("RAG 安全")
    library.add_to_collection(collection.id, "demo", "demo-001")
    library.add_to_collection(collection.id, "demo", "demo-002")
    app = create_app(
        manager=manager,
        mind_map_agent=FixtureMindMapAgent(),
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.put(
            f"/api/library/collections/{collection.id}/note",
            json={"content": "比较两种 RAG 方法"},
        )).status_code == 200
        assert (await client.put(
            f"/api/library/collections/{collection.id}/paper-note",
            json={"source": "demo", "paper_id": "demo-001", "content": "重点论文"},
        )).status_code == 200

        started = await client.post(
            "/api/research",
            json={
                "topic": "RAG 安全",
                "collection_id": collection.id,
                "selected_papers": [{"source": "demo", "paper_id": "demo-001"}],
            },
        )
        completed = await manager.wait(started.json()["task_id"])
        assert completed.status == "completed"

        mapped = await client.post(
            f"/api/library/collections/{collection.id}/mind-maps",
            json={
                "direction": "RAG 安全",
                "selected_papers": [{"source": "demo", "paper_id": "demo-001"}],
            },
        )
        detail = await client.get(f"/api/library/collections/{collection.id}")

        assert mapped.status_code == 201
        assert mapped.json()["paper_ids"] == ["demo-001"]
        assert mapped.json()["map"]["nodes"][0]["label"] == "RAG 安全"
        assert detail.json()["overall_note"] == "比较两种 RAG 方法"
        assert detail.json()["research_run_ids"] == [completed.task_id]
    library.close()


async def test_authenticated_user_can_manage_personal_model_settings(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    auth = AuthenticationService(library, InMemorySessionStore())
    model_settings = PersonalModelSettings(library, tmp_path / "settings.key")
    app = create_app(
        manager=manager,
        auth_service=auth,
        model_settings_service=model_settings,
        require_auth=True,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        registered = await client.post(
            "/api/auth/register",
            json={
                "username": "model-user",
                "email": "model@example.com",
                "password": "password123",
            },
        )
        assert registered.status_code == 201
        initial = await client.get("/api/settings/models")
        assert initial.status_code == 200

        provider = await client.put(
            "/api/settings/providers/qwen",
            json={
                "api_key": "sk-web-secret-1234",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
        )
        agent = await client.put(
            "/api/settings/agents/synthesizer",
            json={
                "provider": "qwen",
                "model_name": "qwen3.7-plus-2026-05-26",
            },
        )
        detail = (await client.get("/api/settings/models")).json()

        assert provider.status_code == 204
        assert agent.status_code == 200
        assert "sk-web-secret-1234" not in str(detail)
        assert next(
            item for item in detail["providers"] if item["provider"] == "qwen"
        )["credential_source"] == "personal"
        assert next(
            item for item in detail["agents"] if item["agent_role"] == "synthesizer"
        )["model_name"] == "qwen3.7-plus-2026-05-26"
    library.close()
