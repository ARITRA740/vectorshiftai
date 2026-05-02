import asyncio
import base64
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, delete_key_redis, get_value_redis

CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET", "").strip()
PRIVATE_ACCESS_TOKEN = (
    os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip()
    or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "").strip()
)
REDIRECT_URI = os.getenv(
    "HUBSPOT_REDIRECT_URI",
    "http://localhost:8000/integrations/hubspot/oauth2callback",
).strip()
SCOPES = tuple(
    scope
    for scope in os.getenv(
        "HUBSPOT_SCOPES",
        "oauth crm.objects.contacts.read crm.objects.companies.read "
        "crm.objects.deals.read crm.objects.tickets.read",
    ).split()
    if scope
)
OAUTH_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
CRM_BASE_URL = "https://api.hubapi.com/crm/v3/objects"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_ITEMS_PER_OBJECT = int(os.getenv("HUBSPOT_MAX_ITEMS_PER_OBJECT", "100"))
CLOSE_WINDOW_HTML = """
<html>
    <script>
        window.close();
    </script>
</html>
""".strip()

HUBSPOT_OBJECTS = (
    {
        "object_type": "contacts",
        "label": "Contacts",
        "properties": (
            "firstname",
            "lastname",
            "email",
            "phone",
            "createdate",
            "lastmodifieddate",
            "hs_lastmodifieddate",
        ),
    },
    {
        "object_type": "companies",
        "label": "Companies",
        "properties": (
            "name",
            "domain",
            "industry",
            "city",
            "createdate",
            "hs_lastmodifieddate",
        ),
    },
    {
        "object_type": "deals",
        "label": "Deals",
        "properties": (
            "dealname",
            "amount",
            "dealstage",
            "pipeline",
            "createdate",
            "hs_lastmodifieddate",
        ),
    },
    {
        "object_type": "tickets",
        "label": "Tickets",
        "properties": (
            "subject",
            "content",
            "hs_pipeline",
            "hs_pipeline_stage",
            "createdate",
            "hs_lastmodifieddate",
        ),
    },
)


def _private_access_token_configured() -> bool:
    return bool(PRIVATE_ACCESS_TOKEN)


def _oauth_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def _ensure_hubspot_connection_configured() -> None:
    if _private_access_token_configured() or _oauth_configured():
        return

    raise HTTPException(
        status_code=500,
        detail=(
            "HubSpot is not configured. Set HUBSPOT_ACCESS_TOKEN for private-app "
            "access or HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET for OAuth."
        ),
    )


def _encode_state(state_data: dict[str, str]) -> str:
    return base64.urlsafe_b64encode(json.dumps(state_data).encode("utf-8")).decode(
        "utf-8"
    )


def _decode_state(encoded_state: str) -> dict[str, str]:
    try:
        return json.loads(base64.urlsafe_b64decode(encoded_state).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.") from exc


def _build_authorization_url(encoded_state: str) -> str:
    query = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(SCOPES),
            "state": encoded_state,
        }
    )
    return f"{OAUTH_AUTHORIZE_URL}?{query}"


def _build_close_window_data_url() -> str:
    return f"data:text/html;charset=utf-8,{quote(CLOSE_WINDOW_HTML)}"


def _parse_hubspot_error(raw_response: str) -> str:
    try:
        response_json = json.loads(raw_response)
    except ValueError:
        return raw_response or "HubSpot request failed."

    if isinstance(response_json, dict):
        message = response_json.get("message")
        if message:
            return message
        errors = response_json.get("errors")
        if errors:
            return json.dumps(errors)

    return "HubSpot request failed."


def _send_http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, str]:
    if params:
        query_string = urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query_string}"

    encoded_body = None
    if data is not None:
        encoded_body = urlencode(data).encode("utf-8")

    request = UrlRequest(url=url, data=encoded_body, method=method.upper())
    for key, value in (headers or {}).items():
        request.add_header(key, value)

    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to reach HubSpot: {exc.reason}",
        ) from exc


def _normalize_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload)
    expires_in = normalized_payload.get("expires_in") or normalized_payload.get(
        "expiresIn"
    )

    if expires_in is not None:
        now = datetime.now(timezone.utc)
        normalized_payload["retrieved_at"] = now.isoformat()
        normalized_payload["expires_at"] = (
            now + timedelta(seconds=int(expires_in))
        ).isoformat()

    return normalized_payload


def _credentials_expired(credentials: dict[str, Any]) -> bool:
    expires_at = credentials.get("expires_at")
    if not expires_at:
        return False

    try:
        expiration_time = datetime.fromisoformat(expires_at)
    except ValueError:
        return False

    refresh_buffer = timedelta(seconds=30)
    return datetime.now(timezone.utc) >= expiration_time - refresh_buffer


def _build_container_item(object_type: str, label: str) -> IntegrationItem:
    return IntegrationItem(
        id=f"hubspot:{object_type}",
        name=label,
        type="Collection",
        directory=True,
        parent_path_or_name="HubSpot",
    )


def _integration_item_type(object_type: str) -> str:
    singular_names = {
        "contacts": "contact",
        "companies": "company",
        "deals": "deal",
        "tickets": "ticket",
    }
    return singular_names.get(object_type, object_type)


def _select_record_name(object_type: str, properties: dict[str, Any], item_id: str) -> str:
    if object_type == "contacts":
        first_name = (properties.get("firstname") or "").strip()
        last_name = (properties.get("lastname") or "").strip()
        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
        return full_name or properties.get("email") or f"Contact {item_id}"

    if object_type == "companies":
        return properties.get("name") or properties.get("domain") or f"Company {item_id}"

    if object_type == "deals":
        return properties.get("dealname") or f"Deal {item_id}"

    if object_type == "tickets":
        subject = properties.get("subject")
        if subject:
            return subject
        content = (properties.get("content") or "").strip()
        return (content[:40] + "...") if len(content) > 40 else content or f"Ticket {item_id}"

    return properties.get("name") or f"{object_type.title()} {item_id}"


def create_integration_item_metadata_object(
    response_json: dict[str, Any],
    object_type: str,
    parent_id: str,
    parent_name: str,
) -> IntegrationItem:
    properties = response_json.get("properties", {})
    item_id = str(response_json.get("id"))
    return IntegrationItem(
        id=f"hubspot:{object_type}:{item_id}",
        name=_select_record_name(object_type, properties, item_id),
        type=_integration_item_type(object_type),
        parent_id=parent_id,
        parent_path_or_name=parent_name,
        creation_time=response_json.get("createdAt") or properties.get("createdate"),
        last_modified_time=response_json.get("updatedAt")
        or properties.get("hs_lastmodifieddate")
        or properties.get("lastmodifieddate"),
        visibility=not response_json.get("archived", False),
    )


async def _exchange_code_for_tokens(code: str) -> dict[str, Any]:
    status_code, response_body = await asyncio.to_thread(
        _send_http_request,
        "POST",
        OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )

    if status_code != 200:
        raise HTTPException(
            status_code=status_code,
            detail=_parse_hubspot_error(response_body),
        )

    return _normalize_token_payload(json.loads(response_body))


async def _refresh_access_token(credentials: dict[str, Any]) -> dict[str, Any]:
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="HubSpot credentials expired and no refresh token is available.",
        )

    status_code, response_body = await asyncio.to_thread(
        _send_http_request,
        "POST",
        OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
    )

    if status_code != 200:
        raise HTTPException(
            status_code=status_code,
            detail=_parse_hubspot_error(response_body),
        )

    refreshed_credentials = _normalize_token_payload(json.loads(response_body))
    refreshed_credentials.setdefault("refresh_token", refresh_token)
    for stable_key in ("hub_id", "hubId", "scope", "scopes"):
        if stable_key in credentials and stable_key not in refreshed_credentials:
            refreshed_credentials[stable_key] = credentials[stable_key]

    return refreshed_credentials


async def _get_valid_access_token(credentials: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if _credentials_expired(credentials):
        if not _oauth_configured():
            raise HTTPException(
                status_code=401,
                detail=(
                    "HubSpot credentials expired and OAuth refresh is unavailable. "
                    "Configure HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET or use "
                    "HUBSPOT_ACCESS_TOKEN."
                ),
            )
        credentials = await _refresh_access_token(credentials)

    access_token = credentials.get("access_token") or credentials.get("accessToken")
    if not access_token and _private_access_token_configured():
        access_token = PRIVATE_ACCESS_TOKEN
        credentials = {
            **credentials,
            "access_token": PRIVATE_ACCESS_TOKEN,
            "auth_type": "private_app",
        }
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="HubSpot credentials are missing an access token.",
        )

    return access_token, credentials


async def _fetch_crm_collection(
    access_token: str,
    object_config: dict[str, Any],
) -> list[dict[str, Any]]:
    object_type = object_config["object_type"]
    properties = ",".join(object_config["properties"])
    after = None
    results: list[dict[str, Any]] = []

    while len(results) < DEFAULT_MAX_ITEMS_PER_OBJECT:
        params: dict[str, Any] = {
            "limit": min(DEFAULT_PAGE_SIZE, DEFAULT_MAX_ITEMS_PER_OBJECT - len(results)),
            "properties": properties,
            "archived": "false",
        }
        if after is not None:
            params["after"] = after

        status_code, response_body = await asyncio.to_thread(
            _send_http_request,
            "GET",
            f"{CRM_BASE_URL}/{object_type}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if status_code != 200:
            raise HTTPException(
                status_code=status_code,
                detail=(
                    f"Failed to load HubSpot {object_type}: "
                    f"{_parse_hubspot_error(response_body)}"
                ),
            )

        payload = json.loads(response_body)
        results.extend(payload.get("results", []))
        after = payload.get("paging", {}).get("next", {}).get("after")
        if after is None:
            break

    return results


async def authorize_hubspot(user_id: str, org_id: str) -> str:
    _ensure_hubspot_connection_configured()

    if _private_access_token_configured():
        await add_key_value_redis(
            f"hubspot_credentials:{org_id}:{user_id}",
            json.dumps(
                {
                    "access_token": PRIVATE_ACCESS_TOKEN,
                    "token_type": "bearer",
                    "auth_type": "private_app",
                }
            ),
            expire=600,
        )
        return _build_close_window_data_url()

    state_data = {
        "state": secrets.token_urlsafe(32),
        "user_id": user_id,
        "org_id": org_id,
    }
    encoded_state = _encode_state(state_data)
    await add_key_value_redis(
        f"hubspot_state:{org_id}:{user_id}",
        json.dumps(state_data),
        expire=600,
    )

    return _build_authorization_url(encoded_state)


async def oauth2callback_hubspot(request: Request) -> HTMLResponse:
    if request.query_params.get("error"):
        raise HTTPException(
            status_code=400,
            detail=request.query_params.get("error_description")
            or request.query_params.get("error"),
        )

    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state")
    if not code or not encoded_state:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters.")

    state_data = _decode_state(encoded_state)
    original_state = state_data.get("state")
    user_id = state_data.get("user_id")
    org_id = state_data.get("org_id")
    if not original_state or not user_id or not org_id:
        raise HTTPException(status_code=400, detail="Invalid OAuth state payload.")

    saved_state = await get_value_redis(f"hubspot_state:{org_id}:{user_id}")
    if not saved_state:
        raise HTTPException(status_code=400, detail="OAuth state not found or expired.")

    saved_state_payload = json.loads(saved_state)
    if saved_state_payload.get("state") != original_state:
        raise HTTPException(status_code=400, detail="State does not match.")

    token_payload, _ = await asyncio.gather(
        _exchange_code_for_tokens(code),
        delete_key_redis(f"hubspot_state:{org_id}:{user_id}"),
    )
    await add_key_value_redis(
        f"hubspot_credentials:{org_id}:{user_id}",
        json.dumps(token_payload),
        expire=600,
    )

    return HTMLResponse(
        content=CLOSE_WINDOW_HTML
    )


async def get_hubspot_credentials(user_id: str, org_id: str) -> dict[str, Any]:
    credentials = await get_value_redis(f"hubspot_credentials:{org_id}:{user_id}")
    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found.")

    await delete_key_redis(f"hubspot_credentials:{org_id}:{user_id}")
    return json.loads(credentials)


async def get_items_hubspot(credentials: str | dict[str, Any]) -> list[IntegrationItem]:
    if isinstance(credentials, str):
        credentials = json.loads(credentials)

    access_token, normalized_credentials = await _get_valid_access_token(credentials)
    hub_id = normalized_credentials.get("hub_id") or normalized_credentials.get("hubId")

    object_results = await asyncio.gather(
        *[
            _fetch_crm_collection(access_token, object_config)
            for object_config in HUBSPOT_OBJECTS
        ]
    )

    items: list[IntegrationItem] = []
    for object_config, records in zip(HUBSPOT_OBJECTS, object_results):
        container_item = _build_container_item(
            object_config["object_type"], object_config["label"]
        )
        items.append(container_item)
        for record in records:
            item = create_integration_item_metadata_object(
                response_json=record,
                object_type=object_config["object_type"],
                parent_id=container_item.id,
                parent_name=container_item.name,
            )
            if hub_id:
                item.drive_id = str(hub_id)
            items.append(item)

    return items
