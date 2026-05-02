const PROD_API_BASE_URL = '/_/backend';
const LOCAL_API_BASE_URL = 'http://localhost:8000';

export function getApiBaseUrl() {
    if (process.env.REACT_APP_API_BASE_URL) {
        return process.env.REACT_APP_API_BASE_URL;
    }

    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
        return LOCAL_API_BASE_URL;
    }

    return PROD_API_BASE_URL;
}
