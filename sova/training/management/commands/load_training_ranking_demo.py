import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from sova.catalog.enum import ClientKind
from sova.catalog.models import B2CClient, Program, University
from sova.interactions.models import (
    Contract,
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    Responsible,
)
from sova.processes.services import workflow_engine_service
from sova.training.enum import TrainingStreamStatus
from sova.training.models import Learner
from sova.training.services.application import training_application_service
from sova.training.services.stream import training_stream_service
from sova.workflows.enum import Audience
from sova.workflows.models import Workflow
from sova.workflows.presets import BASE_B2B_PRESET, BASE_B2C_PRESET
from sova.workflows.services import workflow_template_service

# Метка в комментарии взаимодействия: по ней повторный запуск видит, что демо-данные уже есть
DEMO_PREFIX = "[ranking-demo]"
MANAGER_EMAIL = "kam@kam.ru"

# Программы берутся из каталога по индексу в списке активных программ, упорядоченном по направлению и названию.
# У каждой программы контрагента: (индекс программы, оплативших, не оплативших). Суммы оплативших подобраны так,
# чтобы в рейтинге были и дележи мест (1, 2, 2, 4), и контрагент без места (только не оплатившие).
UNIVERSITY_PLAN: tuple[tuple[str, tuple[tuple[int, int, int], ...]], ...] = (
    ("Ломоносова", ((5, 6, 1), (8, 4, 0), (1, 2, 0))),
    ("Санкт-Петербургский государственный университет", ((5, 5, 0), (6, 4, 1))),
    ("Высшая школа экономики", ((1, 5, 0), (0, 4, 1))),
    ("физико-технический", ((6, 3, 0), (10, 3, 1))),
    ("Уральский федеральный", ((8, 4, 0),)),
    ("Казанский", ((3, 2, 0), (2, 2, 0))),
    ("Томский государственный университет", ((4, 2, 1),)),
    ("Новосибирский государственный университет", ((11, 1, 0),)),
    ("Тюменский государственный университет", ((9, 0, 3),)),
)
B2C_PLAN: tuple[tuple[str, str, str, tuple[tuple[int, int, int], ...]], ...] = (
    ("ООО «Цифровые решения»", ClientKind.LEGAL_ENTITY, "7701000001", ((5, 5, 0), (8, 3, 0))),
    ("ООО «Альфа Консалтинг»", ClientKind.LEGAL_ENTITY, "7701000002", ((11, 4, 1),)),
    ("Иванов Пётр Сергеевич", ClientKind.INDIVIDUAL, "", ((6, 1, 0),)),
    ("Смирнова Анна Игоревна", ClientKind.INDIVIDUAL, "", ((9, 1, 0),)),
    ("Кузнецов Дмитрий Олегович", ClientKind.INDIVIDUAL, "", ((7, 0, 2),)),
)
LAST_NAMES = ("Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов", "Попов", "Волков", "Соколов", "Лебедев", "Козлов")
FIRST_NAMES = ("Алексей", "Мария", "Дмитрий", "Анна", "Сергей", "Елена", "Илья", "Ольга", "Никита", "Татьяна")
FEMALE_FIRST_NAMES = {"Мария", "Анна", "Елена", "Ольга", "Татьяна"}


class Command(BaseCommand):
    help = (
        "Демо-данные для проверки рейтинга каталога: базовые workflow для вузов и B2C (B2C — копия вузовского), "
        "взаимодействия с вузами и B2C-клиентами по разным программам и направлениям с подписанным договором и "
        "запущенным процессом, потоки обучения и обучающиеся — оплатившие (зачисленные) и нет. "
        "Повторный запуск ничего не создаёт, если демо-данные уже есть."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if Interaction.objects.filter(comment__startswith=DEMO_PREFIX).exists():
            self.stdout.write(self.style.WARNING("Демо-данные рейтинга уже созданы — ничего не делаю."))
            return
        programs = list(
            Program.objects.filter(is_active=True, direction__is_active=True)
            .select_related("direction")
            .order_by("direction__name", "name")
        )
        if not programs:
            raise CommandError("В каталоге нет активных программ — сначала загрузите справочники.")
        self.programs = programs
        self.manager = self._manager()
        self.learner_number = 0
        workflows = {audience: self._workflow(audience) for audience in (Audience.B2B, Audience.B2C)}

        used = set()
        for keyword, plan in UNIVERSITY_PLAN:
            university = self._university(keyword, used)
            used.add(university.pk)
            self._interaction(workflows[Audience.B2B], plan, university=university)
        for full_name, kind, inn, plan in B2C_PLAN:
            client, _ = B2CClient.objects.get_or_create(full_name=full_name, defaults={"kind": kind, "inn": inn or None})
            self._interaction(workflows[Audience.B2C], plan, b2c_client=client)

        self.stdout.write(self.style.SUCCESS(
            f"Взаимодействий: {len(UNIVERSITY_PLAN)} с вузами и {len(B2C_PLAN)} с B2C-клиентами, "
            f"обучающихся: {self.learner_number}. Ответственный: {self.manager}."
        ))

    def _manager(self):
        """Ответственный за демо-взаимодействия: КАМ по почте, иначе первый активный пользователь."""
        users = get_user_model().objects.filter(is_active=True)
        manager = users.filter(email__iexact=MANAGER_EMAIL).first() or users.order_by("pk").first()
        if manager is None:
            raise CommandError("В базе нет активных пользователей — некого назначить ответственным.")
        return manager

    def _workflow(self, audience: str) -> Workflow:
        """Базовый workflow аудитории; если его нет — собирается по пресету (для B2C — копия вузовского)."""
        workflow = Workflow.objects.filter(audience=audience, is_base=True, is_active=True).first()
        if workflow is not None:
            return workflow
        spec = BASE_B2B_PRESET if audience == Audience.B2B else BASE_B2C_PRESET
        workflow = Workflow.objects.filter(code=spec.code).first()
        if workflow is None:
            workflow = workflow_template_service.create(spec=spec, is_base=True, created_by=self.manager)
            self.stdout.write(f"Создан шаблон workflow «{workflow.name}».")
        return workflow

    @staticmethod
    def _university(keyword: str, used: set) -> University:
        """Вуз по части названия; если такого нет — любой активный вуз с координатами (он виден на карте)."""
        active = University.objects.filter(is_active=True).exclude(pk__in=used)
        university = (
            active.filter(name__icontains=keyword).order_by("name").first()
            or active.filter(~Q(lat=None), ~Q(lon=None)).order_by("name").first()
        )
        if university is None:
            raise CommandError("В каталоге не хватает активных вузов.")
        return university

    def _interaction(self, workflow: Workflow, plan, university=None, b2c_client=None) -> None:
        """Взаимодействие с подписанным договором и программами, запущенный процесс, потоки и обучающиеся."""
        counterparty = university or b2c_client
        interaction = Interaction.objects.create(
            comment=f"{DEMO_PREFIX} {counterparty}",
            university=university,
            b2c_client=b2c_client,
        )
        Responsible.objects.create(interaction=interaction, manager=self.manager)
        Contract.objects.create(
            interaction=interaction,
            contract_number=f"ДЕМО-{interaction.sequence_number}",
            signed_at=datetime.date.today() - datetime.timedelta(days=30),
        )
        interaction_programs = []
        for index, paid, unpaid in plan:
            program = self.programs[index % len(self.programs)]
            InteractionDirection.objects.get_or_create(interaction=interaction, direction=program.direction)
            interaction_program = InteractionProgram.objects.create(interaction=interaction, program=program)
            for product in program.products.filter(is_active=True).order_by("name")[:2]:
                InteractionProduct.objects.get_or_create(
                    interaction=interaction,
                    product=product,
                    defaults={"interaction_program": interaction_program},
                )
            interaction_programs.append((interaction_program, paid, unpaid))
        workflow_engine_service.start(workflow=workflow, interaction=interaction, started_by=self.manager)

        for interaction_program, paid, unpaid in interaction_programs:
            stream = training_stream_service.create_training_stream(
                interaction_program=interaction_program,
                name=f"{interaction_program.program.name}: поток 1",
                user=self.manager,
                status=TrainingStreamStatus.IN_PROGRESS,
                starts_at=datetime.date.today() - datetime.timedelta(days=14),
                ends_at=datetime.date.today() + datetime.timedelta(days=60),
            )
            application = training_application_service.create_application(
                stream=stream, user=self.manager, comment=DEMO_PREFIX
            )
            for is_paid in (True,) * paid + (False,) * unpaid:
                training_application_service.add_learner(
                    application=application, learner=self._learner(), is_paid=is_paid
                )

    def _learner(self) -> Learner:
        """Новый демо-обучающийся с уникальными контактами."""
        number = self.learner_number
        self.learner_number += 1
        first_name = FIRST_NAMES[number % len(FIRST_NAMES)]
        last_name = LAST_NAMES[(number // len(FIRST_NAMES) + number) % len(LAST_NAMES)]
        if first_name in FEMALE_FIRST_NAMES:
            last_name += "а"
        return Learner.objects.create(
            last_name=last_name,
            first_name=first_name,
            email=f"ranking-demo-{number + 1}@example.test",
            phone=f"7999{number + 1:07d}",
        )
