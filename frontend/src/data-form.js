import { useState } from 'react';
import {
    Box,
    TextField,
    Button,
} from '@mui/material';
import axios from 'axios';
import { getApiBaseUrl } from './api-base-url';

const API_BASE_URL = getApiBaseUrl();

const endpointMapping = {
    'Notion': 'notion',
    'Airtable': 'airtable',
    'HubSpot': 'hubspot',
};

export const DataForm = ({ integrationType, credentials }) => {
    const [loadedData, setLoadedData] = useState(null);
    const endpoint = endpointMapping[integrationType];

    const handleLoad = async () => {
        try {
            const response = await axios.post(`${API_BASE_URL}/integrations/${endpoint}/load`, {
                credentials: JSON.stringify(credentials),
            });
            const data = response.data;
            console.log('Loaded integration data:', data);
            setLoadedData(data);
        } catch (e) {
            alert(e?.response?.data?.detail);
        }
    }

    return (
        <Box display='flex' justifyContent='center' alignItems='center' flexDirection='column' width='100%'>
            <Box display='flex' flexDirection='column' width='100%'>
                <TextField
                    label="Loaded Data"
                    value={loadedData ? JSON.stringify(loadedData, null, 2) : ''}
                    sx={{mt: 2}}
                    InputLabelProps={{ shrink: true }}
                    multiline
                    minRows={12}
                    disabled
                />
                <Button
                    onClick={handleLoad}
                    sx={{mt: 2}}
                    variant='contained'
                >
                    Load Data
                </Button>
                <Button
                    onClick={() => setLoadedData(null)}
                    sx={{mt: 1}}
                    variant='contained'
                >
                    Clear Data
                </Button>
            </Box>
        </Box>
    );
}
