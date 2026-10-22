from app.services import email as mailer

from .conftest import PASSWORD, auth, last_otp, login


def test_register_login_otp_flow(client, admin):
    me = client.get("/v1/auth/me", headers=admin)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    office = client.get("/v1/office", headers=admin).json()
    assert office["razao_social"] == "CONTABIL EXEMPLO LTDA"
    assert office["crc"] == "CE-012345/O-1"
    # aceite dos termos no cadastro
    assert client.get("/v1/terms/pending", headers=admin).json() == []
    assert mailer.outbox[-1]["from"] == "360cash <contato@360cash.tech>"


def test_endpoints_require_auth(client):
    assert client.get("/v1/clients").status_code == 401
    assert client.get("/v1/clients", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_wrong_password_and_lockout(client, admin):
    for _ in range(5):
        r = client.post("/v1/auth/login", json={"email": "maria@contabil.com.br", "password": "errada"})
        assert r.status_code == 401
    r = client.post("/v1/auth/login", json={"email": "maria@contabil.com.br", "password": PASSWORD})
    assert r.status_code == 423


def test_unknown_email_same_error(client):
    r = client.post("/v1/auth/login", json={"email": "ninguem@x.com", "password": "qualquer"})
    assert r.status_code == 401
    assert r.json()["detail"] == "E-mail ou senha inválidos"


def test_wrong_otp_and_attempt_limit(client, admin):
    r = client.post("/v1/auth/login", json={"email": "maria@contabil.com.br", "password": PASSWORD})
    otp_token = r.json()["otp_token"]
    code = last_otp()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/v1/auth/otp/verify", json={"otp_token": otp_token, "code": wrong}).status_code == 401
    # após 5 tentativas o código é invalidado mesmo se correto
    assert client.post("/v1/auth/otp/verify", json={"otp_token": otp_token, "code": code}).status_code == 401


def test_otp_single_use(client, admin):
    r = client.post("/v1/auth/login", json={"email": "maria@contabil.com.br", "password": PASSWORD})
    body = {"otp_token": r.json()["otp_token"], "code": last_otp()}
    assert client.post("/v1/auth/otp/verify", json=body).status_code == 200
    assert client.post("/v1/auth/otp/verify", json=body).status_code == 401


def test_refresh_rotation_and_reuse_detection(client, admin):
    tokens = login(client, "maria@contabil.com.br")
    r = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    # reutilizar o antigo derruba todas as sessões
    assert client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_forgot_and_reset_password(client, admin):
    r = client.post("/v1/auth/password/forgot", json={"email": "maria@contabil.com.br"})
    assert r.status_code == 200
    token = mailer.outbox[-1]["text"].split("token=")[1].split()[0]
    weak = client.post("/v1/auth/password/reset", json={"token": token, "new_password": "fraquinha123"})
    assert weak.status_code == 422
    new_password = "NovaSenha#2026x"
    assert client.post("/v1/auth/password/reset", json={"token": token, "new_password": new_password}).status_code == 200
    assert client.post("/v1/auth/password/reset", json={"token": token, "new_password": new_password}).status_code == 400
    assert client.post("/v1/auth/login", json={"email": "maria@contabil.com.br", "password": PASSWORD}).status_code == 401
    login(client, "maria@contabil.com.br", new_password)
    # e-mail inexistente recebe a mesma resposta
    r2 = client.post("/v1/auth/password/forgot", json={"email": "naoexiste@x.com"})
    assert r2.json() == r.json()


def test_change_password_invalidates_old_tokens(client, admin):
    r = client.post("/v1/auth/password/change", headers=admin,
                    json={"current_password": PASSWORD, "new_password": "Trocada!2026abc"})
    assert r.status_code == 200
    assert client.get("/v1/auth/me", headers=admin).status_code == 401
    tokens = login(client, "maria@contabil.com.br", "Trocada!2026abc")
    assert client.get("/v1/auth/me", headers=auth(tokens)).status_code == 200


def test_security_headers_and_swagger(client):
    r = client.get("/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    spec = client.get("/openapi.json").json()
    assert "/v1/auth/otp/verify" in spec["paths"]
    assert "/v1/clients/{client_id}/reports/dre" in spec["paths"]
