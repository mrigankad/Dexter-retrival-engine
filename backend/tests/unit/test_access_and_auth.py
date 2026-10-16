import time
from datetime import datetime, timedelta

import pytest
from jose import jwt

from src.contracts import RetrievedChunk
from src.core import access
from src.core.auth import JWKSCache, set_jwks_cache, verify_bearer, verify_entra_token
from src.core.config import settings
from src.core.security import TokenData, create_token_pair, verify_access_token


def _user(uid="11111111-1111-1111-1111-111111111111", role="user", groups=None, tenant="t1"):
    return TokenData(user_id=uid, username="u", exp=datetime.utcnow() + timedelta(hours=1), tenant_id=tenant, role=role, groups=groups or [])


def test_principals_and_acl_helpers():
    assert access.principals_for(None) == ["public"]
    p = access.principals_for(_user(groups=["finance"]))
    assert "user:11111111-1111-1111-1111-111111111111" in p and "tenant:t1" in p and "group:finance" in p and "public" in p
    assert access.acl_for_document("o", "t1", "private") == ["user:o"]
    assert access.acl_for_document("o", "t1", "tenant", ["legal"]) == ["group:legal", "tenant:t1", "user:o"]
    assert "public" in access.acl_for_document(None, None, "public")
    assert access.groups_to_column(["b", "a", "a", ""]) == ",a,b," and access.column_to_groups(",a,b,") == ["a", "b"]


def test_access_filters_fail_closed_and_admin_scope(monkeypatch):
    anon = access.access_filters_for(None)
    assert anon.principals == ["public"]
    user = access.access_filters_for(_user(groups=["g"]))
    assert "group:g" in user.principals and user.tenant_id is None
    admin = access.access_filters_for(_user(role="admin"))
    assert admin.principals is None and admin.tenant_id == "t1"
    svc = access.access_filters_for(None, service_caller=True)
    assert svc.principals is None
    monkeypatch.setattr(settings, "acl_enforcement", False)
    assert access.access_filters_for(None).is_empty()


def test_local_jwt_carries_claims():
    pair = create_token_pair("uid", "alice", "a@x.com", tenant_id="acme", role="admin", groups=["finance", "legal"])
    data = verify_access_token(pair.access_token)
    assert data.tenant_id == "acme" and data.role == "admin" and data.groups == ["finance", "legal"] and data.issuer == "local"
    assert verify_bearer(pair.access_token) is not None
    assert verify_bearer("garbage") is None


@pytest.fixture
def rsa_jwks():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwk
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    pub_pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    public_jwk = jwk.construct(pub_pem, algorithm="RS256").to_dict()
    public_jwk.update({"kid": "kid-1", "use": "sig", "alg": "RS256"})
    public_jwk = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in public_jwk.items()}
    cache = JWKSCache("https://example.invalid/keys", ttl_seconds=10_000)
    cache.set_keys({"keys": [public_jwk]})
    set_jwks_cache(cache)
    yield priv_pem
    set_jwks_cache(None)


def _entra_token(priv_pem, **claims):
    now = int(time.time())
    payload = {"iss": "https://login.microsoftonline.com/tenant-123/v2.0", "aud": "api://bodham", "exp": now + 600, "iat": now,
               "oid": "oid-42", "tid": "tenant-123", "preferred_username": "alice@contoso.com", "groups": ["finance"], **claims}
    return jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": "kid-1"})


def test_entra_token_validation(rsa_jwks, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "entra")
    monkeypatch.setattr(settings, "entra_tenant_id", "tenant-123")
    monkeypatch.setattr(settings, "entra_client_id", "api://bodham")
    monkeypatch.setattr(settings, "entra_admin_group", "admins")
    data = verify_bearer(_entra_token(rsa_jwks))
    assert data is not None and data.user_id == "oid-42" and data.tenant_id == "tenant-123" and data.groups == ["finance"]
    assert data.role == "user" and data.issuer == "entra" and data.username == "alice@contoso.com"
    assert verify_bearer(_entra_token(rsa_jwks, groups=["admins"])).role == "admin"
    assert verify_entra_token(_entra_token(rsa_jwks, aud="other")) is None
    assert verify_entra_token(_entra_token(rsa_jwks, exp=int(time.time()) - 10)) is None
    assert verify_entra_token("not.a.jwt") is None
    # local tokens are rejected in entra-only mode but accepted in 'both'
    local = create_token_pair("uid", "bob").access_token
    assert verify_bearer(local) is None
    monkeypatch.setattr(settings, "auth_mode", "both")
    assert verify_bearer(local) is not None and verify_bearer(_entra_token(rsa_jwks)) is not None


def test_mcp_authenticate(monkeypatch):
    from src.mcp_server.server import MCPAuthError, authenticate
    monkeypatch.setattr(settings, "mcp_require_auth", True)
    monkeypatch.setattr(settings, "mcp_api_token", "svc-token")
    with pytest.raises(MCPAuthError):
        authenticate(None)
    with pytest.raises(MCPAuthError):
        authenticate({"authorization": "Bearer nope"})
    svc = authenticate({"Authorization": "Bearer svc-token"})
    assert svc.service and svc.user is None
    token = create_token_pair("uid", "alice", tenant_id="t1", groups=["g"]).access_token
    caller = authenticate({"authorization": f"Bearer {token}"})
    assert not caller.service and caller.user.username == "alice"
    monkeypatch.setattr(settings, "mcp_require_auth", False)
    assert authenticate(None).user is None


def test_mcp_adapter_parsing():
    from types import SimpleNamespace
    from src.knowledge import McpKnowledgeAdapter
    structured = SimpleNamespace(structured_content={"evidence": [{"id": "ev_1", "source": "a.pdf", "page": 2, "content": "alpha", "score": 0.5, "rerank_score": 0.9}]}, content=[])
    chunks = McpKnowledgeAdapter.parse_result(structured)
    assert chunks[0].source == "a.pdf" and chunks[0].page == 2 and chunks[0].rerank_score == 0.9 and chunks[0].backend == "mcp"
    foundry = SimpleNamespace(structured_content=None, content=[SimpleNamespace(text='{"references": [{"id": "0", "docKey": "d7", "rerankerScore": 3.1, "sourceData": {"chunk": "beta", "title": "Doc"}}]}')])
    chunks = McpKnowledgeAdapter.parse_result(foundry)
    assert chunks[0].content == "beta" and chunks[0].source == "Doc" and chunks[0].document_id == "d7"
    plain = SimpleNamespace(structured_content=None, content=[SimpleNamespace(text="just text")])
    assert McpKnowledgeAdapter.parse_result(plain)[0].content == "just text"
    args = McpKnowledgeAdapter(server="http://x", tool_name="knowledge_base_retrieve", auth_token="").build_arguments(
        __import__("src.contracts", fromlist=["RetrievalRequest"]).RetrievalRequest(query="q"))
    assert args["messages"][0]["content"][0]["text"] == "q"
