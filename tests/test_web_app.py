from __future__ import annotations

from repair_requests import create_app


def test_redirects_to_login_when_not_authenticated(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
    client = app.test_client()

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_operator_can_create_and_master_has_limited_access(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
    client = app.test_client()

    with client:
        login = client.post(
            "/login",
            data={"username": "operator", "password": "operator"},
            follow_redirects=False,
        )
        assert login.status_code == 302

        created = client.post(
            "/requests/new",
            data={
                "appliance_type": "Холодильник",
                "appliance_model": "LG",
                "issue_type": "Электрика",
                "problem_description": "Не включается",
                "client_name": "Иванов И.И.",
                "client_phone": "89991234567",
                "technician_username": "master",
            },
            follow_redirects=False,
        )
        assert created.status_code == 302
        assert created.headers["Location"].startswith("/requests/")

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "master", "password": "master"})

        forbidden = client.get("/requests/1/edit", follow_redirects=False)
        assert forbidden.status_code == 403

        allowed = client.get("/requests/1", follow_redirects=False)
        assert allowed.status_code == 200

        work = client.get("/requests/1/work", follow_redirects=False)
        assert work.status_code == 200

