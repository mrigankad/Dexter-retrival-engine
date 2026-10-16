import pytest

from src.data_gateway import SqlPolicy, SqlPolicyError, rows_to_markdown, suggest_chart, validate_chart_spec
from src.data_gateway.models import ColumnInfo, SchemaCatalog, SemanticEntity, SemanticModel, TableInfo, VerifiedQuery
from src.data_gateway.semantic import example_context, match_verified, rank_tables, schema_context

POLICY = SqlPolicy("sqlite", allowed_tables=["sales_orders", "customers"], denied_columns=["customers.ssn", "email"], default_limit=100, hard_limit=1000)


@pytest.mark.parametrize("sql", [
    "SELECT c.name, SUM(o.net_amount) rev FROM sales_orders o JOIN customers c ON o.customer_id=c.id GROUP BY c.name ORDER BY rev DESC",
    "WITH t AS (SELECT * FROM sales_orders) SELECT count(*) FROM t",
    "SELECT product FROM sales_orders UNION SELECT name FROM customers",
    "SELECT * FROM sales_orders WHERE customer_id IN (SELECT id FROM customers WHERE region = 'EMEA')",
    "select net_amount from sales_orders limit 10;",
])
def test_policy_allows_read_only_selects(sql):
    r = POLICY.validate(sql)
    assert r.ok, r.violations
    assert "LIMIT" in r.sql.upper() and r.limit is not None and r.limit <= 1000


@pytest.mark.parametrize("sql,needle", [
    ("DELETE FROM sales_orders", "only SELECT"),
    ("UPDATE sales_orders SET net_amount = 0", "only SELECT"),
    ("INSERT INTO customers (name) VALUES ('x')", "only SELECT"),
    ("DROP TABLE customers", "only SELECT"),
    ("SELECT 1; DROP TABLE x", "exactly one statement"),
    ("SELECT * FROM payroll", "table not allowed: payroll"),
    ("SELECT c.ssn FROM customers c", "column not allowed"),
    ("SELECT email FROM customers", "column not allowed"),
    ("SELECT * FROM customers", "SELECT * not allowed"),
    ("SELECT pg_sleep(10)", "forbidden function"),
    ("SELECT * FROM sales_orders WHERE id IN (SELECT id FROM payroll)", "table not allowed: payroll"),
    ("GRANT ALL ON customers TO bob", "only SELECT"),
    ("PRAGMA table_info(customers)", "only SELECT"),
    ("", "empty"),
    ("SELECT FROM WHERE", "parse error"),
])
def test_policy_blocks(sql, needle):
    r = POLICY.validate(sql)
    assert not r.ok and any(needle in v for v in r.violations), r.violations
    with pytest.raises(SqlPolicyError):
        POLICY.enforce(sql)


def test_policy_limit_handling():
    assert POLICY.validate("SELECT id FROM sales_orders").limit == 100
    assert POLICY.validate("SELECT id FROM sales_orders", limit=20).limit == 20
    assert POLICY.validate("SELECT id FROM sales_orders LIMIT 99999").limit == 1000
    assert POLICY.validate("SELECT id FROM sales_orders LIMIT 5").limit == 5
    open_policy = SqlPolicy("postgres")   # no allowlist: any table, but still read-only
    assert open_policy.validate("SELECT * FROM anything").ok
    assert not open_policy.validate("TRUNCATE TABLE anything").ok


def test_charts_and_markdown():
    assert suggest_chart(["revenue"], [[1234.5]])["type"] == "kpi"
    line = suggest_chart(["month", "revenue"], [["2026-08", 1], ["2026-09", 2]])
    assert line["type"] == "line" and line["x"] == "month" and line["y"] == ["revenue"]
    bar = suggest_chart(["customer", "revenue"], [["ACME", 1], ["Globex", 2]])
    assert bar["type"] == "bar"
    assert suggest_chart(["name", "region"], [["a", "b"]])["type"] == "table"
    assert suggest_chart([], []) is None
    spec = validate_chart_spec({"type": "line", "x": "month", "y": "revenue", "title": "t"}, ["month", "revenue"])
    assert spec["y"] == ["revenue"]
    with pytest.raises(ValueError):
        validate_chart_spec({"type": "pie"}, ["a"])
    with pytest.raises(ValueError):
        validate_chart_spec({"type": "bar", "x": "nope", "y": ["revenue"]}, ["month", "revenue"])
    md = rows_to_markdown(["a", "b"], [[1, None], [2, "x"]])
    assert md.splitlines()[0] == "| a | b |" and "| 1 |  |" in md


def _catalog():
    return SchemaCatalog(connection_id="sales", dialect="sqlite", tables=[
        TableInfo(name="customers", columns=[ColumnInfo(name="id", type="INTEGER", primary_key=True), ColumnInfo(name="name", type="TEXT"), ColumnInfo(name="region", type="TEXT")]),
        TableInfo(name="sales_orders", columns=[ColumnInfo(name="id", type="INTEGER", primary_key=True), ColumnInfo(name="customer_id", type="INTEGER", foreign_key="customers.id"),
                                                ColumnInfo(name="net_amount", type="REAL"), ColumnInfo(name="created_at", type="TEXT")]),
        TableInfo(name="payroll", columns=[ColumnInfo(name="employee", type="TEXT"), ColumnInfo(name="salary", type="REAL")]),
    ])


def test_semantic_ranking_and_context():
    model = SemanticModel(connection_id="sales", entities=[
        SemanticEntity(name="SalesOrder", source="sales_orders", description="Customer sales orders",
                       dimensions={"order_date": "created_at"}, metrics={"revenue": "SUM(net_amount)"},
                       synonyms={"revenue": ["turnover", "sales"]}, relationships={"customer": "sales_orders.customer_id = customers.id"})],
        verified_queries=[VerifiedQuery(question_pattern="total revenue", sql="SELECT SUM(net_amount) AS revenue FROM sales_orders"),
                          VerifiedQuery(question_pattern=r"revenue (for|of) customer (\w+)", sql="SELECT 1")],
        glossary={"revenue": "sum of net_amount on closed orders"})
    ranked = rank_tables(_catalog(), model, "What was the turnover by customer last month?")
    names = [t.name for t, _ in ranked]
    assert names[0] == "sales_orders" and "customers" in names and "payroll" not in names
    ctx = schema_context([t for t, _ in ranked], model)
    assert "metric revenue = SUM(net_amount)" in ctx and "TABLE sales_orders" in ctx and "GLOSSARY" in ctx
    assert match_verified(model, "Total Revenue?").sql.startswith("SELECT SUM")
    assert match_verified(model, "revenue for customer ACME") is not None
    assert match_verified(model, "how many orders") is None
    assert "Q: total revenue" in example_context(model, "what is the total revenue")
