from sova.processes.action_features.handlers.contact_person import (
    CreateContactPersonHandler,
    LinkContactPersonHandler,
    SelectContactPersonHandler,
)
from sova.processes.action_features.handlers.contract import CreateContractHandler

FEATURE_HANDLERS = {
    "contact_person.create": CreateContactPersonHandler(),
    "contact_person.select": SelectContactPersonHandler(),
    "contact_person.link": LinkContactPersonHandler(),
    "contract.create": CreateContractHandler(),
}
