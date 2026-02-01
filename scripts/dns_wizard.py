import json
import os
import sys

# Color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'
BOLD = '\033[1m'

CONFIG_FILE = 'config/dns_mapping.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"{RED}Error loading config: {e}{RESET}")
            return {}
    return {}

def save_config(data):
    if not os.path.exists('config'):
        os.makedirs('config')
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"\n{GREEN}✅ Saved config to {CONFIG_FILE}{RESET}")

def main():
    mappings = load_config()
    comment = mappings.pop("_comment", "Map Node Names to DNS Records.")

    while True:
        print(f"\n{BOLD}🌐 RemnaGuard DNS Mapping Wizard{RESET}")
        print("=======================================")
        
        current_nodes = [k for k in mappings.keys()]
        print(f"Current Mappings: {len(current_nodes)}")
        for i, node in enumerate(current_nodes, 1):
            conf = mappings[node]
            status = "🟠 Proxy" if conf.get('proxied') else "⚪ Direct"
            print(f" {i}. {BOLD}{node}{RESET} -> {conf.get('domain')} ({status})")
            
        print(f"\n{BOLD}Options:{RESET}")
        print(f" [{GREEN}A{RESET}] Add/Edit Mapping")
        print(f" [{RED}D{RESET}] Delete Mapping")
        print(f" [{YELLOW}S{RESET}] Save & Exit")
        print(f" [Q] Quit without saving")
        
        try:
            choice = input(f"\nChoice > ").lower().strip()
        except KeyboardInterrupt:
            print("\nAborted.")
            break
            
        if choice == 'a':
            node = input("Node Name (e.g. Ger-1): ").strip()
            if not node: continue
            domain = input("Domain (e.g. vpn.example.com): ").strip()
            if not domain: continue
            proxied = input("Cloudflare Proxy (y/N)? ").lower().strip().startswith('y')
            
            mappings[node] = {"domain": domain, "proxied": proxied}
            print(f"{GREEN}Added {node}{RESET}")
            
        elif choice == 'd':
            node = input("Node Name to delete: ").strip()
            if node in mappings:
                del mappings[node]
                print(f"{RED}Removed {node}{RESET}")
            else:
                print(f"{YELLOW}Node not found.{RESET}")
                
        elif choice == 's':
            mappings["_comment"] = comment
            save_config(mappings)
            break
            
        elif choice == 'q':
            break

if __name__ == "__main__":
    main()
