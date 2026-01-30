import unittest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.remnawave import RemnawaveClient

class TestRemnawaveClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = RemnawaveClient()
        self.client.url = "http://mock-url"
        self.client.token = "mock-token"
        
    async def asyncTearDown(self):
        await self.client.close()

    @patch("httpx.AsyncClient.request")
    async def test_request_success(self, mock_request):
        # Mock successful JSON response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response

        data = await self.client._request("GET", "/test")
        self.assertEqual(data, {"status": "ok"})

    @patch("httpx.AsyncClient.request")
    async def test_request_json_error(self, mock_request):
        # Mock invalid JSON response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        mock_request.return_value = mock_response

        # Should return None and log error (not crashing)
        data = await self.client._request("GET", "/test")
        self.assertIsNone(data)

if __name__ == "__main__":
    unittest.main()
