# VectorShift Integrations Technical Assessment

This submission completes the HubSpot portion of the assessment end-to-end across the FastAPI backend and React frontend.

## Project Overview

The app lets a user:

1. Choose an integration from the UI.
2. Connect that integration through OAuth.
3. Retrieve integration-specific data and inspect the returned `IntegrationItem` objects.

For this submission, the HubSpot integration now supports:

- OAuth authorization with CSRF-safe state validation
- Secure credential exchange and temporary Redis-backed storage
- Access token refresh when cached credentials are expired
- Loading HubSpot CRM items from contacts, companies, deals, and tickets
- Returning normalized `IntegrationItem` objects grouped by collection

## What Was Implemented

### Backend

- Completed `backend/integrations/hubspot.py`
- Added:
  - OAuth authorize URL generation
  - OAuth callback handling
  - Redis-backed credential retrieval
  - Token normalization and refresh support
  - HubSpot CRM item loading with pagination
  - Conversion of HubSpot records into `IntegrationItem` instances

### Frontend

- Added `frontend/src/integrations/hubspot.js`
- Registered HubSpot in the integration picker
- Added HubSpot to the data-loading endpoint map
- Improved the loaded data field so returned objects are shown as formatted JSON

### Tests

- Added focused backend tests in `backend/tests/test_hubspot.py`
- Verified:
  - OAuth URL and state storage behavior
  - Integration item mapping
  - Expired token refresh path
  - Grouped item loading behavior

## Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- A HubSpot public app with OAuth credentials

### Backend Setup

From `backend/`:

```powershell
Copy-Item .env.example .env
```

Set the following environment variables in your shell or `.env` workflow:

- `HUBSPOT_CLIENT_ID`
- `HUBSPOT_CLIENT_SECRET`
- `HUBSPOT_REDIRECT_URI`
- `HUBSPOT_SCOPES`
- `ALLOWED_ORIGINS`
- `REDIS_HOST`

Install backend dependencies:

```powershell
python -m pip install -r requirements-assessment.txt
```

Note: the provided starter `requirements.txt` appears to be a much larger legacy environment file and is not required to run this assessment. In this workspace it failed on Windows because of an unrelated `pycurl` dependency, so `requirements-assessment.txt` is the verified minimal runtime set for this submission.

Run the API:

```powershell
uvicorn main:app --reload
```

### Frontend Setup

From `frontend/`:

```powershell
npm install
Copy-Item .env.example .env
npm start
```

The UI will be available at `http://localhost:3000` and the backend at `http://localhost:8000`.

Set `REACT_APP_API_BASE_URL` in `frontend/.env` when the frontend should talk to a deployed backend instead of localhost.

## How to Use

1. Open the frontend.
2. Leave or edit the sample `User` and `Organization` values.
3. Select `HubSpot` from the integration dropdown.
4. Click `Connect to HubSpot`.
5. Complete the OAuth flow in the popup.
6. After the popup closes, click `Load Data`.
7. Review the returned `IntegrationItem` payload in the text area or browser console.

## Functionality Notes

The HubSpot loader currently fetches a capped list of records from:

- Contacts
- Companies
- Deals
- Tickets

Each object type is returned under a collection-style parent item such as `Contacts` or `Deals`, followed by child `IntegrationItem` records for each object.

## Assumptions Made

- The assessment archive referenced `hubspot.js`, but the provided frontend starter contained an empty `slack.js`. I treated that as a starter-file mismatch and added a new `hubspot.js` integration component.
- HubSpot record types were chosen based on commonly relevant CRM entities: contacts, companies, deals, and tickets.
- Credentials are stored temporarily in Redis to match the starter project pattern.
- If Redis is not installed locally, the backend falls back to an in-memory store for local demo and assessment use.
- Since HubSpot access tokens are short-lived, refresh support was added for more production-ready behavior.
- The UI continues using the provided popup-and-poll pattern so the implementation stays aligned with the starter architecture.

## Testing

From `backend/`:

```powershell
python -m py_compile main.py integrations\hubspot.py integrations\airtable.py integrations\notion.py tests\test_hubspot.py
python -m pytest -q
```

Validated result in this workspace:

- `4 passed in 0.41s`

## Deployment Notes

The repository is structured as a small monorepo, so the clean deployment approach is to deploy `frontend/` and `backend/` as two separate projects.

### Frontend

- Deploy the `frontend/` directory as a Create React App project
- Set `REACT_APP_API_BASE_URL` to your deployed backend URL

### Backend

- Deploy the `backend/` directory as a FastAPI project
- `backend/index.py` exposes the FastAPI app for Vercel-style Python deployment discovery
- Set:
  - `HUBSPOT_CLIENT_ID`
  - `HUBSPOT_CLIENT_SECRET`
  - `HUBSPOT_REDIRECT_URI`
  - `HUBSPOT_SCOPES`
  - `ALLOWED_ORIGINS`

### HubSpot OAuth

After deployment, update your HubSpot app’s redirect URL to the deployed backend callback, for example:

`https://your-backend-domain/integrations/hubspot/oauth2callback`

## Key Files

- `backend/integrations/hubspot.py`
- `backend/tests/test_hubspot.py`
- `frontend/src/integrations/hubspot.js`
- `frontend/src/integration-form.js`
- `frontend/src/data-form.js`
- `backend/.env.example`
