from dataclasses import dataclass

from sova.interactions.models import InteractionProduct, InteractionProgram
from sova.processes.enum import StageInstanceContextType
from sova.processes.models import ActionInstance


@dataclass
class ActionFeatureContext:
    action_instance: ActionInstance
    interaction: object
    university: object | None
    b2c_client: object | None
    interaction_product: InteractionProduct | None
    interaction_program: InteractionProgram | None
    user: object


def build_context(*, action_instance: ActionInstance, user) -> ActionFeatureContext:
    stage = action_instance.stage_instance
    interaction = stage.workflow_instance.interaction
    product = program = None
    if stage.context_type == StageInstanceContextType.PRODUCT:
        product = InteractionProduct.objects.filter(pk=stage.context_id, interaction=interaction).first()
        if product is None:
            return None
        if product.interaction_program_id:
            program = InteractionProgram.objects.filter(pk=product.interaction_program_id, interaction=interaction).first()
    elif stage.context_type == StageInstanceContextType.PROGRAM:
        program = InteractionProgram.objects.filter(pk=stage.context_id, interaction=interaction).first()
        if program is None:
            return None
    return ActionFeatureContext(
        action_instance=action_instance,
        interaction=interaction,
        university=interaction.university,
        b2c_client=interaction.b2c_client,
        interaction_product=product,
        interaction_program=program,
        user=user,
    )
