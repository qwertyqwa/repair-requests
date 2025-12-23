from __future__ import annotations

from datetime import datetime

from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from repair_requests.domain import (
    ISSUE_TYPES,
    ROLE_LABELS,
    STATUS_LABELS,
    RepairRequest,
    Role,
    RequestStatus,
)
from repair_requests.stats import format_timedelta, requests_summary
from repair_requests.store import SqliteStore

bp = Blueprint("web", __name__)


def get_store() -> SqliteStore:
    store = current_app.extensions.get("store")
    if not isinstance(store, SqliteStore):
        raise RuntimeError("Store is not configured")
    return store


def is_safe_next_url(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/") and not target.startswith("//")


@bp.before_app_request
def load_logged_in_user():
    if request.endpoint == "static":
        return

    username = session.get("username")
    store = get_store()
    user = store.get_user(username) if isinstance(username, str) else None
    if isinstance(username, str) and user is None:
        session.pop("username", None)
    g.user = user
    g.unread_notifications_count = (
        store.unread_notifications_count(user.id) if user is not None else 0
    )

    if request.endpoint == "web.login":
        return
    if user is None:
        next_url = request.full_path
        if next_url.endswith("?"):
            next_url = request.path
        return redirect(url_for("web.login", next=next_url))


def require_roles(*roles: Role) -> None:
    user = getattr(g, "user", None)
    if user is None:
        abort(401)
    if user.role not in roles:
        abort(403)


def ensure_request_access(request_obj: RepairRequest) -> None:
    user = getattr(g, "user", None)
    if user is None:
        abort(401)
    if user.role == Role.MASTER and request_obj.technician_username != user.username:
        abort(403)


@bp.app_template_filter("dt")
def format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    try:
        local = value.astimezone()
    except ValueError:
        local = value
    return local.strftime("%d.%m.%Y %H:%M")


@bp.app_template_filter("role_label")
def role_label(value: Role | str | None) -> str:
    if value is None:
        return "—"
    try:
        role = value if isinstance(value, Role) else Role(value)
    except ValueError:
        return str(value)
    return ROLE_LABELS.get(role, role.value)


@bp.app_template_filter("status_label")
def status_label(value: RequestStatus | str | None) -> str:
    if value is None:
        return "—"
    try:
        status = value if isinstance(value, RequestStatus) else RequestStatus(value)
    except ValueError:
        return str(value)
    return STATUS_LABELS.get(status, status.value)


def parse_status(value: str | None) -> RequestStatus | None:
    if not value:
        return None
    try:
        return RequestStatus(value)
    except ValueError:
        return None


def validate_phone(raw: str) -> str | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 10:
        return None
    if len(digits) > 15:
        return None
    return digits


def validate_request_form(form: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    data: dict[str, str] = {}
    errors: dict[str, str] = {}

    def required(name: str, label: str) -> str:
        value = (form.get(name) or "").strip()
        if not value:
            errors[name] = f"Поле «{label}» обязательно."
        data[name] = value
        return value

    required("appliance_type", "Вид техники")
    required("appliance_model", "Модель")
    issue_type = (form.get("issue_type") or "").strip()
    if issue_type and issue_type not in ISSUE_TYPES:
        errors["issue_type"] = "Выберите тип неисправности из списка."
    data["issue_type"] = issue_type

    required("problem_description", "Описание проблемы")
    required("client_name", "ФИО клиента")

    phone_raw = required("client_phone", "Телефон")
    phone_digits = validate_phone(phone_raw)
    if phone_raw and phone_digits is None:
        errors["client_phone"] = "Телефон должен содержать 10–15 цифр."
    if phone_digits:
        data["client_phone"] = phone_digits

    technician_username = (form.get("technician_username") or "").strip()
    data["technician_username"] = technician_username

    status_raw = (form.get("status") or "").strip()
    if status_raw:
        status = parse_status(status_raw)
        if status is None:
            errors["status"] = "Выберите статус из списка."
        data["status"] = status_raw

    return data, errors


def validate_master_work_form(form: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    data: dict[str, str] = {}
    errors: dict[str, str] = {}

    status_raw = (form.get("status") or "").strip()
    if not status_raw:
        errors["status"] = "Выберите статус."
    else:
        status = parse_status(status_raw)
        if status is None:
            errors["status"] = "Выберите статус из списка."
        data["status"] = status_raw

    return data, errors


@bp.get("/")
def index():
    store = get_store()
    user = g.user
    if user is None:
        abort(401)

    status = parse_status(request.args.get("status"))
    requests_list = store.list_requests()
    if user.role == Role.MASTER:
        requests_list = [r for r in requests_list if r.technician_username == user.username]
    if status is not None:
        requests_list = [r for r in requests_list if r.status == status]

    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    return render_template(
        "index.html",
        requests=requests_list,
        status_filter=status.value if status else "",
        status_choices=status_choices,
        can_manage=user.role in {Role.ADMIN, Role.OPERATOR},
    )


@bp.get("/requests/new")
def request_new():
    require_roles(Role.ADMIN, Role.OPERATOR)
    store = get_store()
    masters = store.list_masters()
    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    return render_template(
        "request_form.html",
        page_title="Новая заявка",
        mode="create",
        request_obj=None,
        form_data={},
        errors={},
        issue_types=ISSUE_TYPES,
        status_choices=status_choices,
        masters=masters,
    )


@bp.post("/requests/new")
def request_create():
    require_roles(Role.ADMIN, Role.OPERATOR)
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    masters = store.list_masters()
    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    form_data, errors = validate_request_form(request.form.to_dict(flat=True))
    if errors:
        flash("Исправьте ошибки в форме.", "error")
        return render_template(
            "request_form.html",
            page_title="Новая заявка",
            mode="create",
            request_obj=None,
            form_data=form_data,
            errors=errors,
            issue_types=ISSUE_TYPES,
            status_choices=status_choices,
            masters=masters,
        )

    technician_username = (form_data.get("technician_username") or "").strip() or None
    issue_type = (form_data.get("issue_type") or "").strip() or None
    created = store.create_request(
        appliance_type=form_data["appliance_type"],
        appliance_model=form_data["appliance_model"],
        issue_type=issue_type,
        problem_description=form_data["problem_description"],
        client_name=form_data["client_name"],
        client_phone=form_data["client_phone"],
        technician_username=technician_username,
        created_by_user_id=user.id,
    )

    flash(f"Заявка №{created.number} создана.", "success")
    return redirect(url_for("web.request_detail", number=created.number))


@bp.get("/requests/<int:number>")
def request_detail(number: int):
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    ensure_request_access(request_obj)

    comments = store.list_comments(number)
    parts = store.list_parts(number)
    history = store.list_history(number)
    return render_template(
        "request_detail.html",
        request_obj=request_obj,
        can_manage=user.role in {Role.ADMIN, Role.OPERATOR},
        is_master=user.role == Role.MASTER,
        comments=comments,
        parts=parts,
        history=history,
    )


@bp.get("/requests/<int:number>/work")
def request_work(number: int):
    require_roles(Role.MASTER)
    store = get_store()
    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    ensure_request_access(request_obj)

    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    comments = store.list_comments(number)
    parts = store.list_parts(number)
    history = store.list_history(number)
    return render_template(
        "request_work.html",
        request_obj=request_obj,
        status_choices=status_choices,
        errors={},
        form_data={},
        comments=comments,
        parts=parts,
        history=history,
    )


@bp.post("/requests/<int:number>/work")
def request_work_update(number: int):
    require_roles(Role.MASTER)
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    ensure_request_access(request_obj)

    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    form_data, errors = validate_master_work_form(request.form.to_dict(flat=True))
    if errors:
        flash(errors.get("__all__", "Исправьте ошибки в форме."), "error")
        return render_template(
            "request_work.html",
            request_obj=request_obj,
            status_choices=status_choices,
            errors=errors,
            form_data=form_data,
        )

    previous_status = request_obj.status
    next_status = parse_status(form_data.get("status"))

    if next_status is None:
        flash("Выберите статус.", "error")
        return redirect(url_for("web.request_work", number=number))

    updated = store.update_request(number, status=next_status, changed_by_user_id=user.id)

    if next_status is not None and next_status != previous_status:
        flash(
            f"Статус изменён: {STATUS_LABELS.get(previous_status)} → {STATUS_LABELS.get(next_status)}.",
            "info",
        )
    flash(f"Заявка №{updated.number} сохранена.", "success")
    return redirect(url_for("web.request_detail", number=updated.number))


@bp.get("/requests/<int:number>/edit")
def request_edit(number: int):
    require_roles(Role.ADMIN, Role.OPERATOR)
    store = get_store()
    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    masters = store.list_masters()
    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    return render_template(
        "request_form.html",
        page_title=f"Редактирование заявки №{number}",
        mode="edit",
        request_obj=request_obj,
        form_data={},
        errors={},
        issue_types=ISSUE_TYPES,
        status_choices=status_choices,
        masters=masters,
    )


@bp.post("/requests/<int:number>/edit")
def request_update(number: int):
    require_roles(Role.ADMIN, Role.OPERATOR)
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)

    masters = store.list_masters()
    status_choices = [(s.value, STATUS_LABELS[s]) for s in RequestStatus]
    form_data, errors = validate_request_form(request.form.to_dict(flat=True))
    if errors:
        flash("Исправьте ошибки в форме.", "error")
        return render_template(
            "request_form.html",
            page_title=f"Редактирование заявки №{number}",
            mode="edit",
            request_obj=request_obj,
            form_data=form_data,
            errors=errors,
            issue_types=ISSUE_TYPES,
            status_choices=status_choices,
            masters=masters,
        )

    previous_status = request_obj.status
    next_status = parse_status(form_data.get("status"))

    issue_type = (form_data.get("issue_type") or "").strip() or None
    updated = store.update_request(
        number,
        appliance_type=form_data["appliance_type"],
        appliance_model=form_data["appliance_model"],
        issue_type=issue_type,
        problem_description=form_data["problem_description"],
        client_name=form_data["client_name"],
        client_phone=form_data["client_phone"],
        technician_username=(form_data.get("technician_username") or "").strip(),
        status=next_status,
        changed_by_user_id=user.id,
    )

    if next_status is not None and next_status != previous_status:
        flash(
            f"Статус изменён: {STATUS_LABELS.get(previous_status)} → {STATUS_LABELS.get(next_status)}.",
            "info",
        )
    flash(f"Заявка №{updated.number} сохранена.", "success")
    return redirect(url_for("web.request_detail", number=updated.number))


@bp.post("/requests/<int:number>/delete")
def request_delete(number: int):
    require_roles(Role.ADMIN, Role.OPERATOR)
    store = get_store()
    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    store.delete_request(number)
    flash(f"Заявка №{number} удалена.", "warning")
    return redirect(url_for("web.index"))


@bp.post("/requests/<int:number>/comments")
def request_add_comment(number: int):
    store = get_store()
    user = g.user
    if user is None:
        abort(401)

    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    ensure_request_access(request_obj)

    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Комментарий не может быть пустым.", "error")
        return redirect(request.referrer or url_for("web.request_detail", number=number))

    store.add_comment(number, user_id=user.id, body=body)
    flash("Комментарий добавлен.", "success")
    return redirect(request.referrer or url_for("web.request_detail", number=number))


@bp.post("/requests/<int:number>/parts")
def request_add_part(number: int):
    require_roles(Role.MASTER)
    store = get_store()
    user = g.user
    if user is None:
        abort(401)

    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    ensure_request_access(request_obj)

    part_name = (request.form.get("part_name") or "").strip()
    qty_raw = (request.form.get("quantity") or "").strip()
    if not part_name:
        flash("Укажите название комплектующей.", "error")
        return redirect(request.referrer or url_for("web.request_work", number=number))
    if not qty_raw.isdigit() or int(qty_raw) <= 0:
        flash("Количество должно быть положительным числом.", "error")
        return redirect(request.referrer or url_for("web.request_work", number=number))

    store.add_part(number, part_name=part_name, quantity=int(qty_raw))
    flash("Комплектующая добавлена.", "success")
    return redirect(request.referrer or url_for("web.request_work", number=number))


@bp.post("/requests/<int:number>/parts/<int:part_id>/delete")
def request_delete_part(number: int, part_id: int):
    require_roles(Role.MASTER)
    store = get_store()
    user = g.user
    if user is None:
        abort(401)

    request_obj = store.get_request(number)
    if not request_obj:
        abort(404)
    ensure_request_access(request_obj)

    store.delete_part(number, part_id)
    flash("Комплектующая удалена.", "warning")
    return redirect(request.referrer or url_for("web.request_work", number=number))


@bp.get("/search")
def search():
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    query = (request.args.get("q") or "").strip()
    status = parse_status(request.args.get("status"))
    technician_username = user.username if user.role == Role.MASTER else None
    results = store.search_requests(
        query=query,
        status=status,
        technician_username=technician_username,
    )

    if query and not results:
        flash("Поиск не дал результатов.", "info")

    status_choices = [("", "Любой")] + [
        (s.value, STATUS_LABELS[s]) for s in RequestStatus
    ]
    return render_template(
        "search.html",
        query=query,
        status_filter=status.value if status else "",
        status_choices=status_choices,
        results=results,
    )


@bp.get("/stats")
def stats():
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    requests_list = store.list_requests()
    if user.role == Role.MASTER:
        requests_list = [r for r in requests_list if r.technician_username == user.username]
    summary = requests_summary(requests_list)
    return render_template(
        "stats.html",
        summary=summary,
        format_timedelta=format_timedelta,
    )


@bp.get("/notifications")
def notifications():
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    items = store.list_notifications(user.id)
    return render_template("notifications.html", notifications=items)


@bp.post("/notifications/<int:notification_id>/read")
def notification_read(notification_id: int):
    store = get_store()
    user = g.user
    if user is None:
        abort(401)
    store.mark_notification_read(user.id, notification_id)
    return redirect(url_for("web.notifications"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    store = get_store()
    if g.user is not None:
        return redirect(url_for("web.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if store.verify_password(username, password):
            session["username"] = username
            flash("Вход выполнен.", "success")
            next_url = request.args.get("next") or url_for("web.index")
            if is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("web.index"))

        flash("Неверный логин или пароль.", "error")

    return render_template("login.html")


@bp.get("/logout")
def logout():
    session.pop("username", None)
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("web.login"))


@bp.app_errorhandler(403)
def forbidden(_error):
    return (
        render_template(
            "error.html",
            title="Доступ запрещен",
            message="Недостаточно прав для выполнения этого действия.",
        ),
        403,
    )


@bp.app_errorhandler(404)
def not_found(_error):
    return (
        render_template(
            "error.html",
            title="Страница не найдена",
            message="Проверьте адрес или вернитесь на главную.",
        ),
        404,
    )
