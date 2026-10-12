from app import app


def test_home():
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert "Xin chào" in response.get_data(as_text=True)


def test_health():
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
