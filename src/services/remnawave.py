import os
import httpx
import logging
import json
from typing import Dict, Optional, Any

class RemnawaveClient:
    def __init__(self):
        self.url = os.getenv("REMNAWAVE_URL")
        self.token = os.getenv("REMNAWAVE_TOKEN")
        
        if not self.url or not self.token:
            logging.error("REMNAWAVE_URL or REMNAWAVE_TOKEN not set in environment")
            
        # Optimization: Persistent Client
        self.client = httpx.AsyncClient(timeout=10.0, limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=30))

    async def _request(self, method: str, endpoint: str, json_data: Dict = None) -> Any:
        if not self.url or not self.token:
            return None


        # Ensure URL doesn't end with slash and endpoint starts with slash
        base_url = self.url.rstrip('/')
        endpoint = endpoint if endpoint.startswith('/') else f"/{endpoint}"
        full_url = f"{base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = await self.client.request(method, full_url, headers=headers, json=json_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP Error {e.response.status_code} for {endpoint}: {e.response.text}")
        except json.JSONDecodeError:
            logging.error(f"Failed to parse JSON response from {endpoint}")
        except Exception as e:
            logging.error(f"Connection Error to Remnawave API: {e}")
        return None

    async def check_connectivity(self) -> bool:
        """Checks if the Panel is reachable."""
        try:
            # Reuse persistent client
            if not self.url:
                 return False
            resp = await self.client.get(self.url.rstrip('/'), follow_redirects=True)
            return resp.status_code < 500
        except Exception as e:
            logging.error(f"Connectivity check failed: {e}")
            return False

    async def close(self):
        """Explicitly close the client session."""
        await self.client.aclose()

    async def get_nodes(self) -> list:
        """
        Fetches list of nodes with traffic stats.
        Endpoint: GET /api/nodes
        """
        data = await self._request("GET", "/api/nodes")
        if not data:
            return []
            
        # Parse based on likely structure (list or dict with 'items')
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
             return data.get("nodes") or data.get("items") or data.get("data") or data.get("result") or data.get("response") or []
        return []
