import asyncio
import httpx
import logging
import os
import yaml
from typing import List, Dict, Optional, Set

class CloudflareService:
    """
    Manages Cloudflare DNS records using a 'Desired State' approach.
    Syncs the actual Cloudflare records to match the 'healthy' IPs from config.
    """
    
    BASE_URL = "https://api.cloudflare.com/client/v4"
    
    def __init__(self, config_path: str = "config.yml"):
        self.token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.config_path = config_path
        self.enabled = bool(self.token) and os.path.exists(config_path)
        self.zone_cache = {} # {domain: zone_id}
        
        if self.enabled:
            logging.info("Cloudflare Service initialized (State-Based).")
            self.config = self._load_config()
        else:
            logging.warning("Cloudflare Service disabled (Missing token or config.yml).")
            self.config = {}

    def _load_config(self) -> Dict:
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Failed to load config.yml: {e}")
            return {}

    async def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_zone_id(self, domain: str) -> Optional[str]:
        """Auto-discover Zone ID for a domain (Cached)."""
        if domain in self.zone_cache:
            return self.zone_cache[domain]
            
        # Extract root domain (simple heuristic: example.com)
        # Improvement: Handle co.uk etc if needed, but for now take last 2 parts
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
                    zone_id = data["result"][0]["id"]
                    self.zone_cache[domain] = zone_id
                    return zone_id
            except Exception as e:
                logging.error(f"Failed to get Zone ID for {domain}: {e}")
        return None

    async def sync_all(self, healthy_ips: Set[str]) -> List[str]:
        """
        Main Sync Entrypoint.
        Ensures that for every configured zone, ONLY the healthy IPs are present.
        Returns a list of changes made.
        """
        if not self.enabled: return []
        
        changes = []
        domains_conf = self.config.get("domains", [])
        
        tasks = []
        for d_conf in domains_conf:
            domain_root = d_conf.get("domain")
            # We need to await zone_id (or cache it) - this part is fast if cached.
            # But strictly speaking we can't fully parallelize getting zone ID without lock or race condition if not cached.
            # But get_zone_id handles its own HTTP call. 
            # Let's parallelize the PER-ZONE work.
            
            # We need to launch a task effectively.
            tasks.append(self._process_domain_sync(d_conf, healthy_ips))
            
        # Run all domain syncs in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, list):
                changes.extend(res)
            elif isinstance(res, Exception):
                logging.error(f"Domain sync failed: {res}")
                
        return changes

    async def _process_domain_sync(self, d_conf: Dict, healthy_ips: Set[str]) -> List[str]:
        """Helper to process a single domain's zones (for parallel execution)."""
        changes = []
        domain_root = d_conf.get("domain")
        zone_id = await self.get_zone_id(domain_root)
        
        if not zone_id:
            logging.error(f"Skipping {domain_root}: Zone ID not found.")
            return []
            
        # Process zones within this domain
        # We can also parallelize THESE if needed, but per-domain parallelism is usually enough.
        # Let's keep it simple: Per-Domain Parallelism.
        
        for zone_conf in d_conf.get("zones", []):
            subdomain = zone_conf.get("name")
            configured_ips = set(zone_conf.get("ips", []))
            proxied = zone_conf.get("proxied", False)
            ttl = zone_conf.get("ttl", 1) 
            
            full_name = f"{subdomain}.{domain_root}" if subdomain != "@" else domain_root
            
            # Determine Target State
            target_ips = configured_ips.intersection(healthy_ips)
            
            if not target_ips:
                logging.warning(f"⚠️ No healthy IPs available for {full_name}!")
            
            # Execute Sync
            zone_changes = await self._sync_zone_records(
                zone_id=zone_id,
                record_name=full_name,
                target_ips=target_ips,
                proxied=proxied,
                ttl=ttl
            )
            changes.extend(zone_changes)
            
        return changes

    async def _sync_zone_records(self, zone_id: str, record_name: str, target_ips: Set[str], proxied: bool, ttl: int) -> List[str]:
        """Reconcile active records with target IPs."""
        changes = []
        async with httpx.AsyncClient() as client:
            headers = await self._get_headers()
            
            # 1. Fetch Existing Records
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/zones/{zone_id}/dns_records",
                    headers=headers,
                    params={"type": "A", "name": record_name}
                )
                data = resp.json()
                if not data["success"]:
                    logging.error(f"Failed to fetch records for {record_name}: {data.get('errors')}")
                    return []
                    
                existing_records = data.get("result", [])
                existing_map = {r["content"]: r["id"] for r in existing_records}
                existing_ips = set(existing_map.keys())
                
                # 2. Calculate Diff
                to_add = target_ips - existing_ips
                to_remove = existing_ips - target_ips
                
                # 3. Apply Removals
                for ip in to_remove:
                    rec_id = existing_map[ip]
                    await client.delete(
                        f"{self.BASE_URL}/zones/{zone_id}/dns_records/{rec_id}",
                        headers=headers
                    )
                    changes.append(f"🗑️ Removed {ip} from {record_name}")
                    logging.info(f"Deleted DNS: {record_name} -> {ip}")
                    
                # 4. Apply Additions
                for ip in to_add:
                    payload = {
                        "type": "A",
                        "name": record_name,
                        "content": ip,
                        "ttl": ttl,
                        "proxied": proxied,
                        "comment": "Managed by RemnaGuard"
                    }
                    await client.post(
                        f"{self.BASE_URL}/zones/{zone_id}/dns_records",
                        headers=headers,
                        json=payload
                    )
                    changes.append(f"📝 Added {ip} to {record_name}")
                    logging.info(f"Created DNS: {record_name} -> {ip}")
                    
            except Exception as e:
                logging.error(f"Sync error for {record_name}: {e}")
                
        return changes
