import httpx
import logging
import os
import json
from typing import Optional, List, Dict

class CloudflareService:
    """Manages Cloudflare DNS records for RemnaGuard nodes."""
    
    BASE_URL = "https://api.cloudflare.com/client/v4"
    
    def __init__(self, mapping_file: str = "config/dns_mapping.json"):
        self.token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
        self.mapping_file = mapping_file
        self.mappings = self._load_mappings()
        self.enabled = bool(self.token and self.mappings)
        
        if self.enabled:
            logging.info("Cloudflare integration enabled.")
        else:
            logging.info("Cloudflare disabled (missing token or mapping).")

    def _load_mappings(self) -> Dict:
        """Load node->dns mappings from JSON."""
        if not os.path.exists(self.mapping_file):
            return {}
        try:
            with open(self.mapping_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load DNS mappings: {e}")
            return {}

    async def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_zone_id(self, domain: str) -> Optional[str]:
        """Auto-discover Zone ID for a domain."""
        if self.zone_id: return self.zone_id
        
        # Extract root domain (simple heuristic)
        root_domain = ".".join(domain.split(".")[-2:])
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/zones",
                    headers=await self._get_headers(),
                    params={"name": root_domain}
                )
                data = resp.json()
                if data["success"] and data["result"]:
                    return data["result"][0]["id"]
            except Exception as e:
                logging.error(f"Failed to get Zone ID for {domain}: {e}")
        return None

    async def update_record(self, node_name: str, ip: str) -> bool:
        """Create or Update A record for the node."""
        if not self.enabled: return False
        
        config = self.mappings.get(node_name)
        if not config: return False # Node not mapped
        
        domain = config["domain"]
        proxied = config.get("proxied", False)
        
        zone_id = await self.get_zone_id(domain)
        if not zone_id:
            logging.error(f"Could not find Zone ID for {domain}")
            return False

        async with httpx.AsyncClient() as client:
            try:
                # 1. Check existing records
                headers = await self._get_headers()
                resp = await client.get(
                    f"{self.BASE_URL}/zones/{zone_id}/dns_records",
                    headers=headers,
                    params={"type": "A", "name": domain}
                )
                records = resp.json().get("result", [])
                
                # 2. Update or Create
                payload = {
                    "type": "A",
                    "name": domain,
                    "content": ip,
                    "ttl": 1, # Auto
                    "proxied": proxied,
                    "comment": "Managed by RemnaGuard"
                }
                
                if records:
                    # Update existing
                    record_id = records[0]["id"]
                    # Only update if content changed
                    if records[0]["content"] == ip and records[0]["proxied"] == proxied:
                        return True # No change needed
                        
                    resp = await client.put(
                        f"{self.BASE_URL}/zones/{zone_id}/dns_records/{record_id}",
                        headers=headers,
                        json=payload
                    )
                else:
                    # Create new
                    resp = await client.post(
                        f"{self.BASE_URL}/zones/{zone_id}/dns_records",
                        headers=headers,
                        json=payload
                    )
                
                success = resp.json().get("success", False)
                if success:
                    logging.info(f"DNS Updated: {domain} -> {ip}")
                else:
                    logging.error(f"DNS Update Failed: {resp.text}")
                return success

            except Exception as e:
                logging.error(f"Cloudflare API error: {e}")
                return False

    async def delete_record(self, node_name: str) -> Optional[str]:
        """Remove A record and return the IP that was deleted."""
        if not self.enabled: return None
        
        config = self.mappings.get(node_name)
        if not config: return None
        
        domain = config["domain"]
        zone_id = await self.get_zone_id(domain)
        if not zone_id: return None

        async with httpx.AsyncClient() as client:
            try:
                headers = await self._get_headers()
                # Find record
                resp = await client.get(
                    f"{self.BASE_URL}/zones/{zone_id}/dns_records",
                    headers=headers,
                    params={"type": "A", "name": domain}
                )
                records = resp.json().get("result", [])
                
                if not records:
                    return None # Already gone
                
                record_id = records[0]["id"]
                params_ip = records[0]["content"] # Capture IP
                
                resp = await client.delete(
                    f"{self.BASE_URL}/zones/{zone_id}/dns_records/{record_id}",
                    headers=headers
                )
                
                if resp.json().get("success"):
                     logging.info(f"DNS Record DELETED: {domain} (was {params_ip})")
                     return params_ip
                return None
                
            except Exception as e:
                logging.error(f"Cloudflare Delete failed: {e}")
                return None
