import { useEffect, useState } from 'react';
import {
    Box,
    Button,
    CircularProgress,
} from '@mui/material';
import axios from 'axios';

export const HubSpotIntegration = ({ user, org, integrationParams, setIntegrationParams }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);

    const handleConnectClick = async () => {
        try {
            setIsConnecting(true);
            const response = await axios.post(
                'http://localhost:8000/integrations/hubspot/authorize',
                {
                    user_id: user,
                    org_id: org,
                },
            );
            const authURL = response?.data;
            const newWindow = window.open(authURL, 'HubSpot Authorization', 'width=600,height=700');

            const pollTimer = window.setInterval(() => {
                if (newWindow?.closed !== false) {
                    window.clearInterval(pollTimer);
                    handleWindowClosed();
                }
            }, 200);
        } catch (e) {
            setIsConnecting(false);
            alert(e?.response?.data?.detail);
        }
    };

    const handleWindowClosed = async () => {
        try {
            const response = await axios.post(
                'http://localhost:8000/integrations/hubspot/credentials',
                {
                    user_id: user,
                    org_id: org,
                },
            );
            const credentials = response.data;

            if (credentials) {
                setIsConnected(true);
                setIntegrationParams((prev) => ({
                    ...prev,
                    credentials,
                    type: 'HubSpot',
                }));
            }
            setIsConnecting(false);
        } catch (e) {
            setIsConnecting(false);
            alert(e?.response?.data?.detail);
        }
    };

    useEffect(() => {
        setIsConnected(Boolean(integrationParams?.credentials));
    }, [integrationParams]);

    return (
        <>
            <Box sx={{ mt: 2 }}>
                Parameters
                <Box display='flex' alignItems='center' justifyContent='center' sx={{ mt: 2 }}>
                    <Button
                        variant='contained'
                        onClick={isConnected ? () => {} : handleConnectClick}
                        color={isConnected ? 'success' : 'primary'}
                        disabled={isConnecting}
                        style={{
                            pointerEvents: isConnected ? 'none' : 'auto',
                            cursor: isConnected ? 'default' : 'pointer',
                            opacity: isConnected ? 1 : undefined,
                        }}
                    >
                        {isConnected
                            ? 'HubSpot Connected'
                            : isConnecting
                                ? <CircularProgress size={20} />
                                : 'Connect to HubSpot'}
                    </Button>
                </Box>
            </Box>
        </>
    );
};
