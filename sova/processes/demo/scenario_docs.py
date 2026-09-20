"""Генерация инструкции (Markdown) и файла HTTP-клиента PyCharm из сценариев `scenarios.py`."""

import json
import re
from pathlib import Path

from sova.processes.demo.scenarios import SCENARIOS, Scenario, Step

LABELS = {
    "setup": "0",
    "linear": "1",
    "branching": "2",
    "products": "3",
    "late_product": "3б",
    "rollback": "4",
    "rollback_products": "4б",
    "rules": "5",
}
_VAR = re.compile(r"^\{\{(\w+)\}\}$")


def _json(value) -> str:
    """JSON без экранирования кириллицы: короткий — в одну строку, длинный — с отступами."""
    compact = json.dumps(value, ensure_ascii=False)
    return compact if len(compact) <= 96 else json.dumps(value, ensure_ascii=False, indent=2)


def _expected(value) -> str:
    """Ожидаемое значение для Markdown: JSON-литерал."""
    return json.dumps(value, ensure_ascii=False)


def _describe_check(path: str, expected) -> str:
    """Проверка ответа человеческим языком."""
    if path.endswith("#"):
        return f"в `{path.removesuffix('#')}` элементов: **{expected}**"
    return f"`{path}` = `{_expected(expected)}`"


def _step_lines(step: Step) -> list[str]:
    """Блок запроса шага для Markdown."""
    lines = [f"{step.method} {step.path}"]
    if step.files:
        lines.append("Content-Type: multipart/form-data")
        lines.append("")
        for name, value in (step.body or {}).items():
            lines.append(f"{name} = {value}")
        for name, filename in step.files.items():
            lines.append(f"{name} = <файл {filename}>")
    elif step.body is not None:
        lines.append("Content-Type: application/json")
        lines.append("")
        lines.extend(_json(step.body).splitlines())
    return lines


def render_step_markdown(label: str, step: Step) -> str:
    """Шаг сценария в Markdown."""
    parts = [f"#### {label}. {step.title}", "", "```http", *_step_lines(step), "```", ""]
    parts.append(f"**Ожидается:** HTTP **{step.status}**" + (":" if step.checks else "."))
    if step.checks:
        parts.append("")
        parts.extend(f"- {_describe_check(path, value)}" for path, value in step.checks.items())
    if step.save:
        saved = ", ".join(f"`{{{{{name}}}}}` ← `{path}`" for name, path in step.save.items())
        parts.append("")
        parts.append(f"**Запомнить из ответа:** {saved}.")
    if step.note:
        parts.append("")
        parts.append(f"> {step.note}")
    parts.append("")
    return "\n".join(parts)


def _prepared_range(key: str) -> str:
    """Диапазон шагов подготовки сценария: `3.1–3.18`."""
    label = LABELS[key]
    count = len(SCENARIOS[key].prepare)
    return f"{label}.1" if count == 1 else f"{label}.1–{label}.{count}"


def render_scenario_markdown(scenario: Scenario) -> str:
    """Сценарий в Markdown: подготовка (её создаёт команда `seed_demo_data`) и выполнение."""
    label = LABELS[scenario.key]
    parts = [f"## Сценарий {label}. {scenario.title}", "", scenario.goal, ""]
    if scenario.requires:
        needed = ", ".join(
            f"«{SCENARIOS[key].title}» (сценарий {LABELS[key]}, шаги {_prepared_range(key)})"
            for key in scenario.requires
        )
        parts += [f"**Сначала выполните подготовку:** {needed}.", ""]
    if scenario.prepare and scenario.steps:
        parts += [
            f"Шаги {_prepared_range(scenario.key)} — **подготовка**: справочники, workflow и взаимодействия. "
            f"Их создаёт команда `manage.py seed_demo_data` (раздел 1), тогда начинайте с первого шага выполнения. "
            "Дальше — **выполнение**: то, что вы проверяете.",
            "",
        ]
    for number, step in enumerate(scenario.all_steps, start=1):
        if number == 1 and scenario.prepare:
            parts += ["### Подготовка", ""]
        if number == len(scenario.prepare) + 1 and scenario.prepare and scenario.steps:
            parts += ["### Выполнение", ""]
        parts.append(render_step_markdown(f"{label}.{number}", step))
    return "\n".join(parts)


_INTRO = (Path(__file__).resolve().parents[3] / "docs" / "manual-testing" / "intro.md").read_text(encoding="utf-8")


def _contents() -> str:
    """Оглавление сценариев."""
    lines = ["## Оглавление сценариев", ""]
    for scenario in SCENARIOS.values():
        lines.append(
            f"- **Сценарий {LABELS[scenario.key]}.** {scenario.title} — "
            f"{len(scenario.prepare)} шагов подготовки и {len(scenario.steps)} выполнения",
        )
    return "\n".join(lines) + "\n"


def render_markdown() -> str:
    """Полная инструкция в Markdown."""
    sections = [_INTRO, _contents()]
    for scenario in SCENARIOS.values():
        sections.append(render_scenario_markdown(scenario))
    return "\n".join(sections).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------------------------------------------------
# Файл для PyCharm HTTP Client
# ---------------------------------------------------------------------------------------------------------------------

_HTTP_HEADER = """# Ручная проверка движка workflow — файл для PyCharm HTTP Client.
# Сгенерирован из sova/processes/tests/scenarios.py командой `.venv/bin/python docs/manual-testing/build.py`.
# Порядок: раздел «Вход», затем сценарии сверху вниз.
# Значения сохраняются в глобальные переменные и подставляются сами.
# Сервер нужно запускать с DJANGO_DEBUG=true. Инструкция: README.md рядом.

@host = http://127.0.0.1:8000
@username = admin
@password = change-me

### Вход 1. Получить CSRF-токен
GET {{host}}/api/auth/me/

> {%
    client.global.set("csrf", response.body.csrfToken);
%}

### Вход 2. Войти как суперпользователь (форма админки)
POST {{host}}/admin/login/
Content-Type: application/x-www-form-urlencoded
Referer: {{host}}/admin/login/

username={{username}}&password={{password}}&csrfmiddlewaretoken={{csrf}}&next=/admin/

### Вход 3. Обновить CSRF-токен после входа
GET {{host}}/api/auth/me/

> {%
    client.test("Вход выполнен", function () { client.assert(response.body.authenticated === true, "не вошли"); });
    client.global.set("csrf", response.body.csrfToken);
%}

"""


def _js_path(path: str) -> str:
    """Путь через точку → выражение JavaScript: `a.0.b` → `a[0].b`."""
    return "".join(f"[{part}]" if part.isdigit() else f".{part}" for part in path.split("."))


def _js_value(value) -> str:
    """Ожидаемое значение → выражение JavaScript (ссылка `{{имя}}` — на сохранённую переменную)."""
    if isinstance(value, str):
        match = _VAR.match(value)
        if match:
            return f'client.global.get("{match.group(1)}")'
    return json.dumps(value, ensure_ascii=False)


def _http_assertions(step: Step) -> list[str]:
    """Проверки и сохранение значений шага на языке HTTP-клиента PyCharm."""
    lines = [
        f'    client.test("HTTP {step.status}", function () {{ '
        f'client.assert(response.status === {step.status}, "получили " + response.status); }});',
    ]
    for path, expected in step.checks.items():
        if path.endswith("#"):
            target = f"response.body{_js_path(path.removesuffix('#'))}.length"
        else:
            target = f"response.body{_js_path(path)}"
        lines.append(
            f'    client.assert({target} === {_js_value(expected)}, "{path.replace(chr(34), chr(39))}: не совпало");',
        )
    for name, path in step.save.items():
        lines.append(f'    client.global.set("{name}", response.body{_js_path(path)});')
    return lines


def render_step_http(label: str, step: Step) -> str:
    """Шаг сценария для HTTP-клиента PyCharm."""
    lines = [f"### {label}. {step.title}", f"{step.method} {{{{host}}}}{step.path}"]
    if step.method != "GET":
        lines.append("X-CSRFToken: {{csrf}}")
    if step.files:
        lines.append("Content-Type: multipart/form-data; boundary=WebAppBoundary")
        lines.append("")
        for name, value in (step.body or {}).items():
            lines += [
                "--WebAppBoundary",
                f'Content-Disposition: form-data; name="{name}"',
                "",
                str(value),
            ]
        for name, filename in step.files.items():
            lines += [
                "--WebAppBoundary",
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"',
                "Content-Type: application/pdf",
                "",
                f"< ./{filename}",
            ]
        lines.append("--WebAppBoundary--")
    elif step.body is not None:
        lines.append("Content-Type: application/json")
        lines.append("")
        lines.extend(_json(step.body).splitlines())
    lines += ["", "> {%", *_http_assertions(step), "%}", ""]
    return "\n".join(lines)


def render_http() -> str:
    """Файл HTTP-клиента PyCharm со всеми сценариями."""
    parts = [_HTTP_HEADER]
    for scenario in SCENARIOS.values():
        label = LABELS[scenario.key]
        parts.append(f"# ==== Сценарий {label}. {scenario.title} ====\n")
        for number, step in enumerate(scenario.all_steps, start=1):
            if number == 1 and scenario.prepare:
                parts.append("# ---- Подготовка (её создаёт `manage.py seed_demo_data`) ----\n")
            if number == len(scenario.prepare) + 1 and scenario.prepare and scenario.steps:
                parts.append("# ---- Выполнение ----\n")
            parts.append(render_step_http(f"{label}.{number}", step))
    return "\n".join(parts).rstrip("\n") + "\n"
