from sova.processes.action_features.handlers.contact_person import (
    CreateContactPersonHandler,
    DeactivateContactPersonHandler,
    LinkContactPersonHandler,
    SelectContactPersonHandler,
    UpdateContactPersonHandler,
)
from sova.processes.action_features.handlers.contract import CreateContractHandler

FEATURE_HANDLERS = {
    "contact_person.create": CreateContactPersonHandler(),
    "contact_person.select": SelectContactPersonHandler(),
    "contact_person.link": LinkContactPersonHandler(),
    "contact_person.update": UpdateContactPersonHandler(),
    "contact_person.deactivate": DeactivateContactPersonHandler(),
    "contract.create": CreateContractHandler(),
}
