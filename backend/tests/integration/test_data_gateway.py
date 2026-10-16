from typing import Dict, List

import pytest

from fakes import FakeLLM
from src.contracts import Intent
from src.data_gateway import DataQueryError, DataQueryService, SemanticModel
from src.data_gateway.models import VerifiedQuery


class SequenceLLM(FakeLLM):
    """Scripted SQL generator: successive 'Schema (relevant tables only)' prompts get successive replies."""

    def __init__(self, sql_replies: List[str], **kw):
        super().__init__(**kw)
        self.sql_replies = list(sql_replies)

    def _reply(self, messages):
        text = "\n".join(m["content"] for m in messages)
        if "Schema (relevant tables only)" in text and self.sql_replies:
            return self.sql_replies.pop(0)
        return super()._reply(messages)


def _json_sql(sql: str, **extra) -> str:
    import json
    return json.dumps({"sql": sql, "explanation": "test", "needs_clarification": False, **extra})


@pytest.mark.asyncio
async def test_connection_manager_discovery_and_execution(demo_db):
    from src.data_gateway import get_connection_manager
    manager = get_connection_manager()
    assert (await manager.test("sales"))["tables"] == 2        # payroll excluded by allowlist
    catalog = await manager.discover("sales")
    so = catalog.table("sales_orders")
    assert so is not None and any(c.foreign_key == "customers.id" for c in so.columns)
    cols, rows, truncated, latency = await manager.execute("sales", "SELECT name FROM customers ORDER BY id LIMIT 2", max_rows=1)
    assert cols == ["name"] and rows == [["ACME"]] and truncated


@pytest.mark.asyncio
async def test_query_service_generation_retry_and_policy(demo_db):
    llm = SequenceLLM([
        _json_sql("DELETE FROM sales_orders"),                                   # rejected by policy → retry with feedback
        _json_sql("SELECT c.name AS customer, SUM(o.net_amount) AS revenue FROM sales_orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.name ORDER BY revenue DESC",
                  chart={"type": "bar", "x": "customer", "y": ["revenue"]}),
    ])
    from src.data_gateway.generator import SqlGenerator
    service = DataQueryService(generator=SqlGenerator(llm=llm))
    result = await service.query("revenue by customer")
    assert result.source == "generated" and result.columns == ["customer", "revenue"]
    assert result.rows[0] == ["Globex", 5600.0] and result.row_count == 3 and "LIMIT" in result.sql
    assert service.chart_for(result)["type"] == "bar"
    assert "Fix it" in "\n".join(m["content"] for m in llm.calls[-1]["messages"])   # policy feedback was fed back
    ev = service.to_evidence(result, 1)
    assert ev.type == "sql" and ev.metadata["sql"] == result.sql and "| customer | revenue |" in ev.snippet

    # exhausted retries → DataQueryError
    bad = DataQueryService(generator=SqlGenerator(llm=SequenceLLM([_json_sql("SELECT ssn FROM customers"), _json_sql("SELECT * FROM payroll")])))
    with pytest.raises(DataQueryError) as exc:
        await bad.query("show me everything")
    assert "not allowed" in str(exc.value)

    # clarification
    clar = DataQueryService(generator=SqlGenerator(llm=SequenceLLM(['{"sql": "", "needs_clarification": true, "clarification": "Which revenue: gross or net?"}'])))
    with pytest.raises(DataQueryError) as exc:
        await clar.query("what is revenue")
    assert exc.value.clarification == "Which revenue: gross or net?"


@pytest.mark.asyncio
async def test_verified_query_skips_llm(demo_db):
    llm = SequenceLLM([])
    from src.data_gateway.generator import SqlGenerator
    service = DataQueryService(generator=SqlGenerator(llm=llm))
    service.semantic.set(SemanticModel(connection_id="sales", verified_queries=[
        VerifiedQuery(question_pattern="total revenue", sql="SELECT SUM(net_amount) AS total_revenue FROM sales_orders", description="all orders")]))
    result = await service.query("Total revenue")
    assert result.source == "verified" and result.rows == [[8150.0]] and not llm.calls
    assert service.chart_for(result)["type"] == "kpi"
    raw = await service.run_sql("SELECT region, COUNT(*) AS n FROM customers GROUP BY region")
    assert raw.source == "raw" and raw.row_count == 3


@pytest.mark.asyncio
async def test_engine_data_and_hybrid_intents(demo_db, indexed_policy, services):
    from src.data_gateway.generator import SqlGenerator
    from src.data_gateway.service import set_data_query_service
    from src.orchestrator import RetrievalEngine

    sql = "SELECT substr(created_at,1,7) AS month, SUM(net_amount) AS revenue FROM sales_orders GROUP BY month ORDER BY month"
    llm = SequenceLLM([_json_sql(sql), _json_sql(sql)], responses={
        "Evidence:": "Revenue was 3,250 in 2026-10 after 3,700 in 2026-09 [1]. The policy caps hotel stays at 220 USD [2].",
    })
    service = DataQueryService(generator=SqlGenerator(llm=llm))
    set_data_query_service(service)
    engine = RetrievalEngine(llm=llm)
    assert engine.executor.data_service.available

    events = [e async for e in engine.answer_stream("What was total revenue by month this year?")]
    names = [e.event for e in events]
    assert "table" in names and "chart" in names and "progress" in names
    stages = [e.data["stage"] for e in events if e.event == "progress"]
    assert "querying_data" in stages and "retrieving" not in stages
    answer = engine.last_answer
    assert answer.intent == Intent.DATA and answer.evidence[0].type == "sql" and answer.citations
    assert {b.type for b in answer.blocks} == {"table", "chart"}
    chart = next(b for b in answer.blocks if b.type == "chart").data
    assert chart["type"] == "line" and chart["x"] == "month"

    hybrid = await engine.answer("Why did revenue decline last month according to the policy document?")
    assert hybrid.intent == Intent.HYBRID
    assert {e.type for e in hybrid.evidence} == {"document", "sql"}
    assert any(e.source_name.endswith("(SQL)") for e in hybrid.evidence)
    assert [c.marker for c in hybrid.citations] == ["[1]", "[2]"]

    # without any data connection the same question is a knowledge question
    from src.data_gateway.connections import reset_connection_manager
    reset_connection_manager()
    set_data_query_service(DataQueryService(generator=SqlGenerator(llm=llm)))
    engine2 = RetrievalEngine(llm=llm)
    plain = await engine2.answer("What was total revenue by month this year?")
    assert plain.intent == Intent.KNOWLEDGE


@pytest.mark.asyncio
async def test_data_api(client, auth_headers, demo_db, tmp_path):
    from src.data_gateway.generator import SqlGenerator
    from src.data_gateway.service import set_data_query_service
    llm = SequenceLLM([_json_sql("SELECT name, region FROM customers ORDER BY name")])
    set_data_query_service(DataQueryService(generator=SqlGenerator(llm=llm)))

    conns = (await client.get("/data/connections", headers=auth_headers)).json()["connections"]
    assert conns[0]["id"] == "sales" and conns[0]["url"] == "***"
    assert (await client.post("/data/connections/sales/test", headers=auth_headers)).json()["status"] == "ok"
    catalog = (await client.post("/data/connections/sales/discover", headers=auth_headers)).json()
    assert {t["name"] for t in catalog["tables"]} == {"customers", "sales_orders"}

    suggested = (await client.post("/data/connections/sales/semantic/suggest", headers=auth_headers)).json()
    assert any(e["name"] == "SalesOrders" and "total_net_amount" in e["metrics"] for e in suggested["entities"])
    suggested["verified_queries"] = [{"question_pattern": "how many customers", "sql": "SELECT COUNT(*) AS customers FROM customers"}]
    r = await client.put("/data/connections/sales/semantic", headers=auth_headers, json=suggested)
    assert r.status_code == 200 and r.json()["verified_queries"][0]["approved_by"] == "admin"
    assert (await client.get("/data/connections/sales/semantic", headers=auth_headers)).json()["entities"]

    r = await client.post("/data/query", headers=auth_headers, json={"question": "How many customers?"})
    assert r.status_code == 200 and r.json()["source"] == "verified" and r.json()["rows"] == [[3]] and r.json()["chart"]["type"] == "kpi"
    r = await client.post("/data/query", headers=auth_headers, json={"question": "list customers and regions"})
    assert r.status_code == 200 and r.json()["source"] == "generated" and r.json()["row_count"] == 3

    r = await client.post("/data/sql", headers=auth_headers, json={"sql": "DELETE FROM customers"})
    assert r.status_code == 403 and "policy" in r.json()["detail"]
    r = await client.post("/data/sql", headers=auth_headers, json={"sql": "SELECT region, COUNT(*) AS n FROM customers GROUP BY region", "limit": 2})
    assert r.status_code == 200 and r.json()["row_count"] == 2 and r.json()["truncated"]
    v = (await client.post("/data/validate", headers=auth_headers, json={"sql": "SELECT ssn FROM customers"})).json()
    assert not v["ok"] and v["violations"]
    ctx = (await client.get("/data/connections/sales/context", headers=auth_headers, params={"question": "orders by customer"})).json()
    assert ctx["tables"] and "TABLE" in ctx["schema_context"]
    log = (await client.get("/data/queries", headers=auth_headers)).json()["queries"]
    assert len(log) >= 4 and any(q["status"] == "error" for q in log)

    # non-admin: can query, cannot run raw SQL or manage connections
    r = await client.post("/auth/register", json={"username": "ann", "email": "ann@example.com", "password": "secret1"})
    ann = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/data/sql", headers=ann, json={"sql": "SELECT 1"})).status_code == 403
    assert (await client.delete("/data/connections/sales", headers=ann)).status_code == 403
    assert (await client.post("/data/query", headers=ann, json={"question": "How many customers?"})).status_code == 200
    assert (await client.delete("/data/connections/sales", headers=auth_headers)).json()["status"] == "deleted"
    assert (await client.get("/data/connections", headers=auth_headers)).json()["connections"] == []
