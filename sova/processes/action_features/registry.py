from sova.processes.action_features.handlers.contact_person import (
    CreateContactPersonHandler,
    DeactivateContactPersonHandler,
    LinkContactPersonHandler,
    SelectContactPersonHandler,
    UpdateContactPersonHandler,
)
from sova.processes.action_features.handlers.contract import (
    CreateContractHandler,
    MarkContractCorrectedHandler,
    MarkContractSentHandler,
    SignContractHandler,
    UpdateContractHandler,
    UploadContractFileHandler,
)
from sova.processes.action_features.handlers.interaction_composition import (
    AddInteractionDirectionHandler,
    AddInteractionProductHandler,
    AddInteractionProgramHandler,
    RemoveInteractionDirectionHandler,
    RemoveInteractionProductHandler,
    RemoveInteractionProgramHandler,
)
from sova.processes.action_features.handlers.responsible import (
    AssignResponsibleHandler,
    UnassignResponsibleHandler,
)
from sova.processes.action_features.handlers.training import CreateTrainingStreamHandler

FEATURE_HANDLERS = {
    "contact_person.create": CreateContactPersonHandler(),
    "contact_person.select": SelectContactPersonHandler(),
    "contact_person.link": LinkContactPersonHandler(),
    "contact_person.update": UpdateContactPersonHandler(),
    "contact_person.deactivate": DeactivateContactPersonHandler(),
    "responsible.assign": AssignResponsibleHandler(),
    "responsible.unassign": UnassignResponsibleHandler(),
    "interaction_direction.add": AddInteractionDirectionHandler(),
    "interaction_direction.remove": RemoveInteractionDirectionHandler(),
    "interaction_program.add": AddInteractionProgramHandler(),
    "interaction_program.remove": RemoveInteractionProgramHandler(),
    "interaction_product.add": AddInteractionProductHandler(),
    "interaction_product.remove": RemoveInteractionProductHandler(),
    "contract.create": CreateContractHandler(),
    "contract.update": UpdateContractHandler(),
    "contract.sign": SignContractHandler(),
    "contract.file.upload": UploadContractFileHandler(),
    "contract.mark_sent": MarkContractSentHandler(),
    "contract.mark_corrected": MarkContractCorrectedHandler(),
    "training.create": CreateTrainingStreamHandler(),
}
