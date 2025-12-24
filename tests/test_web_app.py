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


def test_master_can_add_comment_and_parts_and_operator_gets_notification(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
    client = app.test_client()

    with client:
        client.post("/login", data={"username": "operator", "password": "operator"})
        client.post(
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
        )

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "master", "password": "master"})

        client.post("/requests/1/comments", data={"body": "Провёл диагностику."})
        client.post("/requests/1/parts", data={"part_name": "ТЭН", "quantity": "2"})
        client.post("/requests/1/work", data={"status": "ready"})

        detail = client.get("/requests/1")
        page = detail.get_data(as_text=True)
        assert "Провёл диагностику." in page
        assert "ТЭН" in page
        assert "× 2" in page
        assert "Новая" in page
        assert "Готова к выдаче" in page

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "operator", "password": "operator"})

        notifications = client.get("/notifications")
        page = notifications.get_data(as_text=True)
        assert "Заявка №1" in page
        assert "Готова к выдаче" in page


def test_manager_can_assign_helper_extend_deadline_and_receive_help_request(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
    client = app.test_client()

    with client:
        client.post("/login", data={"username": "admin", "password": "admin"})
        created_user = client.post(
            "/admin/users",
            data={
                "username": "master2",
                "password": "master2",
                "full_name": "Мастер 2",
                "role": "master",
                "is_active": "1",
            },
            follow_redirects=False,
        )
        assert created_user.status_code == 302

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "operator", "password": "operator"})
        created = client.post(
            "/requests/new",
            data={
                "appliance_type": "Плита",
                "appliance_model": "Hansa",
                "issue_type": "Механика",
                "problem_description": "Не включается",
                "client_name": "Сидоров С.С.",
                "client_phone": "89991112233",
                "technician_username": "master",
            },
            follow_redirects=False,
        )
        assert created.status_code == 302

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "manager", "password": "manager"})

        manage_page = client.get("/requests/1/manage")
        assert manage_page.status_code == 200

        add_helper = client.post(
            "/requests/1/assignees",
            data={"master_username": "master2", "role": "assistant"},
            follow_redirects=False,
        )
        assert add_helper.status_code == 302

        extend = client.post(
            "/requests/1/deadline",
            data={"new_due_at": "2030-01-01T10:00", "client_confirmed": "1", "note": "Согласовано по телефону"},
            follow_redirects=False,
        )
        assert extend.status_code == 302

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "master2", "password": "master2"})

        work = client.get("/requests/1/work", follow_redirects=False)
        assert work.status_code == 200

        notifications = client.get("/notifications")
        page = notifications.get_data(as_text=True)
        assert "Вас привлекли к заявке №1" in page
        assert "продлён срок выполнения" in page

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "master", "password": "master"})

        help_request = client.post(
            "/requests/1/help",
            data={"message": "Не получается подобрать запчасть."},
            follow_redirects=False,
        )
        assert help_request.status_code == 302

    with client:
        client.get("/logout")
        client.post("/login", data={"username": "manager", "password": "manager"})

        notifications = client.get("/notifications")
        page = notifications.get_data(as_text=True)
        assert "Запрос помощи по заявке №1" in page
