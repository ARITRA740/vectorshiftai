from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from integrations.airtable import authorize_airtable, get_items_airtable, oauth2callback_airtable, get_airtable_credentials
from integrations.notion import authorize_notion, get_items_notion, oauth2callback_notion, get_notion_credentials
from integrations.hubspot import authorize_hubspot, get_hubspot_credentials, get_items_hubspot, oauth2callback_hubspot

app = FastAPI()

origins = [
    "http://localhost:3000",  # React app address
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IntegrationAuthRequest(BaseModel):
    user_id: str
    org_id: str


class IntegrationLoadRequest(BaseModel):
    credentials: str

@app.get('/')
def read_root():
    return {'Ping': 'Pong'}


# Airtable
@app.post('/integrations/airtable/authorize')
async def authorize_airtable_integration(payload: IntegrationAuthRequest):
    return await authorize_airtable(payload.user_id, payload.org_id)

@app.get('/integrations/airtable/oauth2callback')
async def oauth2callback_airtable_integration(request: Request):
    return await oauth2callback_airtable(request)

@app.post('/integrations/airtable/credentials')
async def get_airtable_credentials_integration(payload: IntegrationAuthRequest):
    return await get_airtable_credentials(payload.user_id, payload.org_id)

@app.post('/integrations/airtable/load')
async def get_airtable_items(payload: IntegrationLoadRequest):
    return await get_items_airtable(payload.credentials)


# Notion
@app.post('/integrations/notion/authorize')
async def authorize_notion_integration(payload: IntegrationAuthRequest):
    return await authorize_notion(payload.user_id, payload.org_id)

@app.get('/integrations/notion/oauth2callback')
async def oauth2callback_notion_integration(request: Request):
    return await oauth2callback_notion(request)

@app.post('/integrations/notion/credentials')
async def get_notion_credentials_integration(payload: IntegrationAuthRequest):
    return await get_notion_credentials(payload.user_id, payload.org_id)

@app.post('/integrations/notion/load')
async def get_notion_items(payload: IntegrationLoadRequest):
    return await get_items_notion(payload.credentials)

# HubSpot
@app.post('/integrations/hubspot/authorize')
async def authorize_hubspot_integration(payload: IntegrationAuthRequest):
    return await authorize_hubspot(payload.user_id, payload.org_id)

@app.get('/integrations/hubspot/oauth2callback')
async def oauth2callback_hubspot_integration(request: Request):
    return await oauth2callback_hubspot(request)

@app.post('/integrations/hubspot/credentials')
async def get_hubspot_credentials_integration(payload: IntegrationAuthRequest):
    return await get_hubspot_credentials(payload.user_id, payload.org_id)

@app.post('/integrations/hubspot/load')
@app.post('/integrations/hubspot/get_hubspot_items')
async def load_hubspot_data_integration(payload: IntegrationLoadRequest):
    return await get_items_hubspot(payload.credentials)
