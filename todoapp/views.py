import json
from functools import wraps
from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ToDo


def _json_body(request) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _get_param(request, data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
        if key in request.POST and request.POST.get(key) not in (None, ""):
            return request.POST.get(key)
    return default


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    value_str = str(value).strip().lower()
    if value_str in {"1", "true", "yes", "on"}:
        return True
    if value_str in {"0", "false", "no", "off"}:
        return False
    return default


def require_login(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"ok": False, "error": "authentication required"}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper


@csrf_exempt
def login_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    data = _json_body(request)
    username = _get_param(request, data, "username", "Username")
    password = _get_param(request, data, "password", "Password")
    print(f"Login attempt: username={username}, password={password}")

    if not username or not password:
        return JsonResponse({"ok": False, "error": "username and password required"}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"ok": False, "error": "invalid credentials"}, status=401)

    login(request, user)
    return JsonResponse({"ok": True, "user": {"id": user.id, "username": user.username}})


@csrf_exempt
def logout_view(request):
    if request.method not in {"POST", "GET"}:
        return JsonResponse({"ok": False, "error": "POST or GET required"}, status=405)

    logout(request)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_login
def create_todo(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    data = _json_body(request)
    title = _get_param(request, data, "title", "Title")
    text = _get_param(request, data, "text", "Text", default="")
    upload = request.FILES.get("file") or request.FILES.get("File")

    if not title:
        return JsonResponse({"ok": False, "error": "title required"}, status=400)

    todo = ToDo.objects.create(user=request.user, title=title, text=text, file=upload)

    return JsonResponse(
        {
            "ok": True,
            "todo": {
                "id": todo.id,
                "title": todo.title,
                "text": todo.text,
                "done": todo.done,
                "file": request.build_absolute_uri(todo.file.url) if todo.file else None,
            },
        }
    )


@csrf_exempt
@require_login
def mark_done(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    data = _json_body(request)
    todo_id = _get_param(request, data, "id", "todo_id", "ToDoId")
    done_value = _get_param(request, data, "done", "Done")

    if not todo_id:
        return JsonResponse({"ok": False, "error": "todo id required"}, status=400)

    try:
        todo = ToDo.objects.get(id=todo_id, user=request.user)
    except ToDo.DoesNotExist:
        return JsonResponse({"ok": False, "error": "todo not found"}, status=404)

    todo.done = _parse_bool(done_value, default=True)
    todo.save(update_fields=["done"])

    return JsonResponse({"ok": True, "todo": {"id": todo.id, "done": todo.done}})


@csrf_exempt
@require_login
def get_todos(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "GET required"}, status=405)

    todos = (
        ToDo.objects.filter(user=request.user)
        .order_by("-created_at")
        .all()
    )

    items = []
    for todo in todos:
        items.append(
            {
                "id": todo.id,
                "title": todo.title,
                "text": todo.text,
                "done": todo.done,
                "file": request.build_absolute_uri(todo.file.url) if todo.file else None,
                "created_at": todo.created_at.isoformat(),
            }
        )

    return JsonResponse({"ok": True, "todos": items})


@csrf_exempt
@require_login
def delete_all_todos(request):
    if request.method not in {"POST", "DELETE"}:
        return JsonResponse({"ok": False, "error": "POST or DELETE required"}, status=405)

    deleted_count, _ = ToDo.objects.filter(user=request.user).delete()
    return JsonResponse({"ok": True, "deleted": deleted_count})
