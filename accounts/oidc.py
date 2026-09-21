from urllib.parse import urlencode

from django.conf import settings


def provider_logout_url(request) -> str:
    params = {"post_logout_redirect_uri": f"{settings.APP_PUBLIC_URL}/"}
    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token
    else:
        params["client_id"] = settings.KEYCLOAK_CLIENT_ID

    endpoint = (
        f"{settings.KEYCLOAK_PUBLIC_REALM_URL}/protocol/openid-connect/logout"
    )
    return f"{endpoint}?{urlencode(params)}"
