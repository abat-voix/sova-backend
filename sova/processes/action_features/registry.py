from sova.processes.action_features.handlers.contact_person import (
    CreateContactPersonHandler,
    SelectContactPersonHandler,
)

FEATURE_HANDLERS = {
    "contact_person.create": CreateContactPersonHandler(),
    "contact_person.select": SelectContactPersonHandler(),
}
