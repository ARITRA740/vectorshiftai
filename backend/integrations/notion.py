import asyncio
import base64
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, delete_key_redis, get_value_redis

CLIENT_ID = 'XXX'
CLIENT_SECRET = 'XXX'
encoded_client_id_secret = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()

REDIRECT_URI = 'http://localhost:8000/integrations/notion/oauth2callback'
authorization_url = f'https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&response_type=code&owner=user&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fintegrations%2Fnotion%2Foauth2callback'


def _send_http_request(url: str, *, method='GET', headers=None, data=None, json_body=None):
    body = None
    if data is not None:
        body = data.encode('utf-8') if isinstance(data, str) else data
    elif json_body is not None:
        body = json.dumps(json_body).encode('utf-8')

    request = UrlRequest(url=url, data=body, method=method.upper())
    for key, value in (headers or {}).items():
        request.add_header(key, value)

    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read().decode('utf-8')
    except HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', errors='replace')
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f'Unable to reach Notion: {exc.reason}') from exc


async def authorize_notion(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = json.dumps(state_data)
    await add_key_value_redis(f'notion_state:{org_id}:{user_id}', encoded_state, expire=600)

    return f'{authorization_url}&state={encoded_state}'


async def oauth2callback_notion(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error'))
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(encoded_state)

    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state = await get_value_redis(f'notion_state:{org_id}:{user_id}')
    saved_state_payload = json.loads(saved_state if isinstance(saved_state, str) else saved_state.decode('utf-8'))

    if not saved_state or original_state != saved_state_payload.get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    response_status, response_body = await asyncio.to_thread(
        _send_http_request,
        'https://api.notion.com/v1/oauth/token',
        method='POST',
        json_body={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        },
        headers={
            'Authorization': f'Basic {encoded_client_id_secret}',
            'Content-Type': 'application/json',
        }
    )
    await delete_key_redis(f'notion_state:{org_id}:{user_id}')

    if response_status != 200:
        raise HTTPException(status_code=response_status, detail=response_body)

    await add_key_value_redis(f'notion_credentials:{org_id}:{user_id}', response_body, expire=600)

    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)


async def get_notion_credentials(user_id, org_id):
    credentials = await get_value_redis(f'notion_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials if isinstance(credentials, str) else credentials.decode('utf-8'))
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'notion_credentials:{org_id}:{user_id}')

    return credentials


def _recursive_dict_search(data, target_key):
    if target_key in data:
        return data[target_key]

    for value in data.values():
        if isinstance(value, dict):
            result = _recursive_dict_search(value, target_key)
            if result is not None:
                return result
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result = _recursive_dict_search(item, target_key)
                    if result is not None:
                        return result
    return None


def create_integration_item_metadata_object(
    response_json: str,
) -> IntegrationItem:
    name = _recursive_dict_search(response_json['properties'], 'content')
    parent_type = (
        ''
        if response_json['parent']['type'] is None
        else response_json['parent']['type']
    )
    if response_json['parent']['type'] == 'workspace':
        parent_id = None
    else:
        parent_id = (
            response_json['parent'][parent_type]
        )

    name = _recursive_dict_search(response_json, 'content') if name is None else name
    name = 'multi_select' if name is None else name
    name = response_json['object'] + ' ' + name

    integration_item_metadata = IntegrationItem(
        id=response_json['id'],
        type=response_json['object'],
        name=name,
        creation_time=response_json['created_time'],
        last_modified_time=response_json['last_edited_time'],
        parent_id=parent_id,
    )

    return integration_item_metadata


async def get_items_notion(credentials) -> list[IntegrationItem]:
    credentials = json.loads(credentials)
    response_status, response_body = await asyncio.to_thread(
        _send_http_request,
        'https://api.notion.com/v1/search',
        method='POST',
        headers={
            'Authorization': f'Bearer {credentials.get("access_token")}',
            'Notion-Version': '2022-06-28',
        },
    )

    if response_status == 200:
        results = json.loads(response_body)['results']
        list_of_integration_item_metadata = []
        for result in results:
            list_of_integration_item_metadata.append(
                create_integration_item_metadata_object(result)
            )

        print(list_of_integration_item_metadata)
        return list_of_integration_item_metadata
    return []
