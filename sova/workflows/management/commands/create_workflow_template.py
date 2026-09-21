from dataclasses import replace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from sova.processes.models import WorkflowInstance
from sova.workflows.enum import Audience
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowStage,
)
from sova.workflows.presets import BASE_B2B_PRESET
from sova.workflows.schemas import WorkflowSpec
from sova.workflows.services import WorkflowTemplateError, workflow_template_service


class Command(BaseCommand):
    help = (
        "Создаёт шаблон workflow по готовой декларации: этапы, действия, исходы, "
        "связи этапов и зависимости действий. Дальше шаблон правят через API или Django Admin."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--code",
            default=BASE_B2B_PRESET.code,
            help=f"Код шаблона. По умолчанию {BASE_B2B_PRESET.code}.",
        )
        parser.add_argument(
            "--name",
            default=None,
            help="Название шаблона. По умолчанию — из декларации.",
        )
        parser.add_argument(
            "--audience",
            choices=[value for value, _label in Audience.choices],
            default=None,
            help="Аудитория шаблона. По умолчанию — из декларации.",
        )
        parser.add_argument(
            "--base",
            action="store_true",
            help="Сделать шаблон базовым для аудитории (базовый — один на аудиторию).",
        )
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Удалить шаблон с таким кодом и собрать заново. Запрещено, если по нему идут процессы.",
        )
        parser.add_argument(
            "--username",
            default=None,
            help="Пользователь, от имени которого создаётся шаблон: попадёт в автора и в журнал изменений.",
        )

    def handle(self, *args, **options) -> None:
        spec = self._build_spec(options=options)
        created_by = self._resolve_user(username=options["username"])

        try:
            with transaction.atomic():
                self._clear_existing(code=spec.code, recreate=options["recreate"])
                workflow = workflow_template_service.create(
                    spec=spec,
                    is_base=options["base"],
                    created_by=created_by,
                )
        except WorkflowTemplateError as error:
            raise CommandError(f"Ошибка в декларации шаблона: {error}") from error

        self._report(workflow=workflow)

    def _build_spec(self, options: dict) -> WorkflowSpec:
        """Применяет переопределения командной строки к декларации шаблона."""
        overrides = {"code": options["code"]}
        if options["name"] is not None:
            overrides["name"] = options["name"]
        if options["audience"] is not None:
            overrides["audience"] = options["audience"]
        return replace(BASE_B2B_PRESET, **overrides)

    def _resolve_user(self, username: str | None) -> AbstractBaseUser | None:
        """Находит пользователя по имени: без него шаблон создаётся без автора."""
        if not username:
            return None
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"Пользователь «{username}» не найден.")
        return user

    def _clear_existing(self, code: str, recreate: bool) -> None:
        """
        Освобождает код шаблона.

        Существующий шаблон удаляется только по явному `--recreate` и только пока по нему не
        запущено ни одного процесса: удаление шаблона каскадом снесло бы историю процессов.
        """
        existing = Workflow.objects.filter(code=code).first()
        if existing is None:
            return
        if not recreate:
            raise CommandError(
                f"Шаблон с кодом «{code}» уже существует. "
                f"Задайте другой код через --code или пересоберите его через --recreate.",
            )
        started = WorkflowInstance.objects.filter(workflow=existing).count()
        if started:
            raise CommandError(
                f"По шаблону «{code}» уже запущен процесс ({started} шт.): пересоздание удалило бы их историю. "
                f"Создайте новый шаблон с другим кодом через --code.",
            )
        existing.delete()

    def _report(self, workflow: Workflow) -> None:
        """Печатает состав собранного шаблона."""
        counts = (
            f"этапов: {WorkflowStage.objects.filter(workflow=workflow).count()}, "
            f"связей этапов: {StageTransition.objects.filter(from_stage__workflow=workflow).count()}, "
            f"действий: {WorkflowAction.objects.filter(stage__workflow=workflow).count()}, "
            f"исходов: {ActionOutcome.objects.filter(action__stage__workflow=workflow).count()}, "
            f"зависимостей: {ActionDependency.objects.filter(action__stage__workflow=workflow).count()}, "
            f"переходов по исходам: "
            f"{ActionTransition.objects.filter(target_action__stage__workflow=workflow).count()}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Шаблон «{workflow.name}» ({workflow.code}, аудитория {workflow.audience}) создан: {counts}.",
            ),
        )
        self.stdout.write(f"id шаблона: {workflow.pk}")
        self.stdout.write(
            "Запуск процесса по шаблону: POST /api/processes/workflow-instances/ "
            '{"workflow": "<id>", "interaction": "<id взаимодействия>"}.',
        )
