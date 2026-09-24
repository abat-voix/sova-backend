from sova.processes.action_features.handlers.contact_person import (
    CreateContactPersonHandler,
    LinkContactPersonHandler,
    SelectContactPersonHandler,
)

FEATURE_HANDLERS = {
    "contact_person.create": CreateContactPersonHandler(),
    "contact_person.select": SelectContactPersonHandler(),
    "contact_person.link": LinkContactPersonHandler(),
}
