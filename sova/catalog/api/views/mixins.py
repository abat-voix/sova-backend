from accounts.policy import Action


class CatalogPolicyMixin:
    """Единая политика CRUD для справочников каталога."""

    policy_actions = {
        "list": Action.CATALOG_READ,
        "retrieve": Action.CATALOG_READ,
        "create": Action.CATALOG_CREATE,
        "update": Action.CATALOG_UPDATE,
        "partial_update": Action.CATALOG_UPDATE,
        "destroy": Action.CATALOG_DELETE,
    }
