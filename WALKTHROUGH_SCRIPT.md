# 3-5 Minute Walkthrough Script

## 1. Intro

"This project completes the HubSpot portion of VectorShift's integrations technical assessment. The goal was to implement a production-quality HubSpot integration in the provided FastAPI and React starter app, following the same overall pattern as the Airtable and Notion examples."

## 2. High-Level Flow

"From the UI, a user selects HubSpot, clicks connect, completes OAuth in a popup, and then loads HubSpot data. On the backend, we generate a secure OAuth URL, validate the callback state, exchange the authorization code for tokens, store credentials temporarily in Redis, and then use those credentials to fetch HubSpot CRM objects."

## 3. Backend Tour

"The main implementation lives in `backend/integrations/hubspot.py`. There are five main responsibilities here."

"First, `authorize_hubspot` builds the HubSpot authorization URL and stores a short-lived state object in Redis for CSRF protection."

"Second, `oauth2callback_hubspot` validates the callback, exchanges the code for tokens, normalizes the token payload, and stores the credentials temporarily for the frontend to retrieve."

"Third, `get_hubspot_credentials` returns those credentials once the popup flow is finished."

"Fourth, I added refresh-aware token handling. HubSpot access tokens expire quickly, so if cached credentials are expired, the integration can refresh them before loading data."

"Fifth, `get_items_hubspot` loads several CRM object types, specifically contacts, companies, deals, and tickets, paginates through results, and converts them into `IntegrationItem` objects."

## 4. Data Modeling Decisions

"I chose to return a collection-style parent item for each HubSpot object type, like Contacts or Deals, followed by child items for the actual records. That keeps the output organized and shows hierarchy clearly without changing the existing `IntegrationItem` structure."

"For naming, each object type uses practical fallbacks. For example, contacts prefer full name, then email, while companies prefer company name, then domain."

## 5. Frontend Tour

"On the frontend, I added `frontend/src/integrations/hubspot.js`, registered HubSpot in the integration selector, and wired the load-data form to the HubSpot backend endpoint."

"I also improved the result display so loaded data is shown as formatted JSON instead of a raw object string. That makes the demo clearer and makes debugging easier."

"I also removed hardcoded localhost API URLs and made the frontend use an environment-based API base URL, which makes the app much easier to deploy."

## 6. Testing

"I added backend tests in `backend/tests/test_hubspot.py`. These validate the OAuth URL and state behavior, item mapping, expired token refresh logic, and grouped item loading behavior."

"In this environment, the tests pass with four passing checks."

"I also added deployment-oriented changes: configurable backend CORS origins, a Vercel-friendly backend entrypoint, and frontend environment variables for the API base URL."

## 7. Demo Flow

"For the demo, I would start Redis, run the FastAPI app, run the React frontend, select HubSpot, connect with a test HubSpot app, and then click Load Data. The output should show grouped `IntegrationItem` objects for the selected HubSpot CRM entities."

## 8. Close

"The final result is a clean, production-oriented HubSpot integration that matches the starter architecture, handles real OAuth concerns like state validation and token refresh, and is packaged with tests and setup documentation for review."
