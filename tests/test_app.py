def test_healthz_reports_ready(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.get_json()["release"] == "admin-credential-v2"


def test_security_headers_are_present(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "object-src 'none'" in response.headers["Content-Security-Policy"]
