from src.connectors import ConnectorConfig, SourceItem, list_connector_types, resolve_secret
from src.connectors.confluence import map_confluence_restrictions
from src.connectors.google_drive import map_drive_permissions
from src.connectors.microsoft_graph import map_graph_permissions
from src.connectors.sync import acl_for_item


def test_registry_and_secrets(monkeypatch):
    assert {t["type"] for t in list_connector_types()} == {"local_folder", "web", "s3", "sharepoint", "google_drive", "confluence"}
    monkeypatch.setenv("MY_SECRET", "s3cr3t")
    assert resolve_secret("env:MY_SECRET") == "s3cr3t" and resolve_secret("plain") == "plain" and resolve_secret(None) is None
    cfg = ConnectorConfig(type="web", name="w", settings={"api_token": "env:MY_SECRET"})
    assert cfg.secret("api_token") == "s3cr3t" and cfg.secret("missing", "d") == "d"


def test_graph_permission_mapping():
    perms = [
        {"grantedToV2": {"user": {"id": "oid-1", "displayName": "A"}}},
        {"grantedToIdentitiesV2": [{"group": {"id": "g-1"}}, {"user": {"email": "B@Contoso.com"}}]},
        {"link": {"scope": "organization"}},
        {"link": {"scope": "anonymous"}},
    ]
    assert map_graph_permissions(perms, "tenant:t1") == ["group:g-1", "public", "tenant:t1", "user:b@contoso.com", "user:oid-1"]
    assert "tenant:t1" not in map_graph_permissions([{"link": {"scope": "organization"}}], None)


def test_drive_and_confluence_mapping():
    perms = [{"type": "user", "emailAddress": "A@x.com"}, {"type": "group", "emailAddress": "team@x.com"},
             {"type": "domain", "domain": "x.com"}, {"type": "anyone"}]
    assert map_drive_permissions(perms, "tenant:x") == ["group:team@x.com", "public", "tenant:x", "user:a@x.com"]
    data = {"read": {"restrictions": {"user": {"results": [{"accountId": "acc-1"}]}, "group": {"results": [{"id": "grp-9"}]}}}}
    assert map_confluence_restrictions(data) == ["group:grp-9", "user:acc-1"]
    assert map_confluence_restrictions({}) == []


def test_acl_for_item_rules():
    item = SourceItem(external_id="1", title="a.pdf", file_type="pdf", principals=["user:oid-1", "group:g-1"])
    tenant_cfg = ConnectorConfig(type="web", name="w", tenant_id="t1", visibility="tenant", shared_groups=["legal"], settings={"urls": ["x"]})
    assert acl_for_item(tenant_cfg, item) == ["group:g-1", "group:legal", "tenant:t1", "user:oid-1"]
    tenant_cfg.inherit_source_acl = False
    assert acl_for_item(tenant_cfg, item) == ["group:legal", "tenant:t1"]
    source_cfg = ConnectorConfig(type="web", name="w", tenant_id="t1", visibility="source", settings={"urls": ["x"]})
    assert acl_for_item(source_cfg, item) == ["group:g-1", "user:oid-1"]
    assert acl_for_item(source_cfg, SourceItem(external_id="2", title="b.pdf", file_type="pdf")) == ["user:nobody"]
    assert not SourceItem(external_id="3", title="x.exe", file_type="exe").supported()
