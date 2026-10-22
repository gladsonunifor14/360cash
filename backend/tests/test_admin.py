from app.services import email as mailer

from .conftest import auth, login


def _invite(client, admin, **kw):
    body = {"name": "Ana Operadora", "email": "ana@contabil.com.br", "role": "contador", **kw}
    return client.post("/v1/users", headers=admin, json=body)


def _accept_invite(client, email, password="Equipe#Senha2026"):
    token = mailer.outbox[-1]["text"].split("token=")[1].split()[0]
    assert client.post("/v1/auth/password/reset", json={"token": token, "new_password": password}).status_code == 200
    return auth(login(client, email, password))


def test_user_management(client, admin, client_company):
    r = _invite(client, admin)
    assert r.status_code == 201
    ana = r.json()
    assert _invite(client, admin).json()["erros"][0]["loc"] == ["body", "email"]
    bad = _invite(client, admin, email="sem-arroba")
    assert bad.json()["detail"] == "O campo 'E-mail' deve ser um e-mail válido (ex.: nome@empresa.com.br)"
    r = _invite(client, admin, email="x@y.com", role="cliente")
    assert r.status_code == 422 and r.json()["detail"] == "O campo 'Empresa' é obrigatório para usuários do tipo cliente"

    ana_h = _accept_invite(client, "ana@contabil.com.br")
    assert client.get("/v1/auth/me", headers=ana_h).status_code == 200
    assert client.get("/v1/users", headers=ana_h).status_code == 403  # contador não administra usuários

    # promove a cliente vinculado à empresa e depois desativa (encerra a sessão)
    r = client.patch(f"/v1/users/{ana['id']}", headers=admin, json={"role": "cliente", "client_id": client_company["id"]})
    assert r.json()["role"] == "cliente" and r.json()["client_id"] == client_company["id"]
    assert client.post(f"/v1/users/{ana['id']}/deactivate", headers=admin).status_code == 200
    assert client.get("/v1/auth/me", headers=ana_h).status_code == 401
    assert client.post(f"/v1/users/{ana['id']}/resend-invite", headers=admin).status_code == 409
    assert client.post(f"/v1/users/{ana['id']}/reactivate", headers=admin).status_code == 200
    r = client.post(f"/v1/users/{ana['id']}/resend-invite", headers=admin)
    assert r.status_code == 200 and mailer.outbox[-1]["to"] == ["ana@contabil.com.br"]

    # administrador não remove o próprio perfil
    me = client.get("/v1/auth/me", headers=admin).json()
    r = client.patch(f"/v1/users/{me['id']}", headers=admin, json={"role": "contador"})
    assert r.status_code == 422 and r.json()["erros"][0]["loc"][-1] == "role"

    audit = client.get("/v1/audit", headers=admin, params={"entity": "users", "entity_id": ana["id"]}).json()
    assert any(a["changes"] and "role" in a["changes"] for a in audit)


def test_terms_versions_and_evidence(client, admin):
    hist = client.get("/v1/terms/history", headers=admin).json()
    assert {t["kind"] for t in hist} == {"privacidade", "confidencialidade", "uso"}
    assert all(t["is_current"] and t["acceptances"] == 1 for t in hist)

    body = "Nova política de privacidade revisada pelo jurídico do escritório, com encarregado nomeado. " * 2
    r = client.post("/v1/terms", headers=admin, json={"kind": "privacidade", "title": "Política v2", "body": body})
    assert r.status_code == 201 and r.json()["version"] == 2
    short = client.post("/v1/terms", headers=admin, json={"kind": "uso", "title": "X", "body": "curto"})
    assert "O campo 'Texto' deve ter pelo menos 50 caracteres" in short.json()["detail"]

    hist = {(t["kind"], t["version"]): t for t in client.get("/v1/terms/history", headers=admin).json()}
    assert hist[("privacidade", 2)]["is_current"] and not hist[("privacidade", 1)]["is_current"]
    pending = client.get("/v1/terms/pending", headers=admin).json()
    assert [t["version"] for t in pending] == [2]
    client.post("/v1/terms/accept", headers=admin)
    ev = client.get("/v1/terms/acceptances", headers=admin).json()
    assert ev[0]["user_name"] == "Maria Contadora" and ev[0]["term_version"] == 2 and len(ev[0]["content_sha256"]) == 64
