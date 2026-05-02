import asyncio
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

redis_client_stub = types.ModuleType("redis_client")


async def _noop_async(*args, **kwargs):
    return None


redis_client_stub.add_key_value_redis = _noop_async
redis_client_stub.delete_key_redis = _noop_async
redis_client_stub.get_value_redis = _noop_async
sys.modules.setdefault("redis_client", redis_client_stub)

from integrations import hubspot


def test_authorize_hubspot_stores_state_and_builds_expected_url(monkeypatch):
    captured = {}

    async def fake_add_key_value_redis(key, value, expire=None):
        captured["key"] = key
        captured["value"] = value
        captured["expire"] = expire

    monkeypatch.setattr(hubspot, "CLIENT_ID", "test-client-id")
    monkeypatch.setattr(hubspot, "CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(
        hubspot,
        "SCOPES",
        ("oauth", "crm.objects.contacts.read", "crm.objects.companies.read"),
    )
    monkeypatch.setattr(hubspot, "add_key_value_redis", fake_add_key_value_redis)

    authorization_url = asyncio.run(hubspot.authorize_hubspot("user-123", "org-456"))
    query_params = parse_qs(urlparse(authorization_url).query)

    assert query_params["client_id"] == ["test-client-id"]
    assert query_params["scope"] == [
        "oauth crm.objects.contacts.read crm.objects.companies.read"
    ]
    assert captured["key"] == "hubspot_state:org-456:user-123"
    assert captured["expire"] == 600

    stored_state = json.loads(captured["value"])
    assert stored_state["user_id"] == "user-123"
    assert stored_state["org_id"] == "org-456"


def test_create_integration_item_metadata_object_prefers_contact_name():
    item = hubspot.create_integration_item_metadata_object(
        response_json={
            "id": "123",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-02T00:00:00Z",
            "properties": {
                "firstname": "Ada",
                "lastname": "Lovelace",
                "email": "ada@example.com",
            },
        },
        object_type="contacts",
        parent_id="hubspot:contacts",
        parent_name="Contacts",
    )

    assert item.id == "hubspot:contacts:123"
    assert item.name == "Ada Lovelace"
    assert item.type == "contact"
    assert item.parent_id == "hubspot:contacts"
    assert item.parent_path_or_name == "Contacts"


def test_get_valid_access_token_refreshes_expired_credentials(monkeypatch):
    refreshed_credentials = {
        "access_token": "new-access-token",
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    }

    async def fake_refresh_access_token(credentials):
        assert credentials["refresh_token"] == "refresh-token"
        return refreshed_credentials

    monkeypatch.setattr(hubspot, "CLIENT_ID", "test-client-id")
    monkeypatch.setattr(hubspot, "CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(hubspot, "_refresh_access_token", fake_refresh_access_token)

    expired_credentials = {
        "access_token": "expired-token",
        "refresh_token": "refresh-token",
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    }

    access_token, normalized_credentials = asyncio.run(
        hubspot._get_valid_access_token(expired_credentials)
    )

    assert access_token == "new-access-token"
    assert normalized_credentials == refreshed_credentials


def test_get_items_hubspot_returns_grouped_items(monkeypatch):
    async def fake_get_valid_access_token(credentials):
        return credentials["access_token"], credentials

    async def fake_fetch_crm_collection(access_token, object_config):
        assert access_token == "access-token"
        records_by_type = {
            "contacts": [
                {
                    "id": "1",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-02T00:00:00Z",
                    "properties": {
                        "firstname": "Ada",
                        "lastname": "Lovelace",
                        "email": "ada@example.com",
                    },
                }
            ],
            "companies": [
                {
                    "id": "2",
                    "createdAt": "2026-01-03T00:00:00Z",
                    "updatedAt": "2026-01-04T00:00:00Z",
                    "properties": {
                        "name": "Analytical Engines Ltd",
                        "domain": "analytical.example.com",
                    },
                }
            ],
            "deals": [],
            "tickets": [
                {
                    "id": "3",
                    "createdAt": "2026-01-05T00:00:00Z",
                    "updatedAt": "2026-01-06T00:00:00Z",
                    "properties": {
                        "subject": "Onboarding question",
                    },
                }
            ],
        }
        return records_by_type[object_config["object_type"]]

    monkeypatch.setattr(hubspot, "_get_valid_access_token", fake_get_valid_access_token)
    monkeypatch.setattr(hubspot, "_fetch_crm_collection", fake_fetch_crm_collection)

    items = asyncio.run(
        hubspot.get_items_hubspot(
            json.dumps({"access_token": "access-token", "hub_id": 999})
        )
    )

    directory_items = [item for item in items if item.directory]
    record_items = [item for item in items if not item.directory]

    assert [item.name for item in directory_items] == [
        "Contacts",
        "Companies",
        "Deals",
        "Tickets",
    ]
    assert len(record_items) == 3

    contact_item = next(item for item in record_items if item.type == "contact")
    company_item = next(item for item in record_items if item.type == "company")
    ticket_item = next(item for item in record_items if item.type == "ticket")

    assert contact_item.parent_id == "hubspot:contacts"
    assert company_item.parent_id == "hubspot:companies"
    assert ticket_item.parent_id == "hubspot:tickets"
    assert contact_item.drive_id == "999"
