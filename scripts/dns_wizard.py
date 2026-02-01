import os
import sys
import time
import shutil

# Try importing yaml
try:
    import yaml
except ImportError:
    print("❌ Error: PyYAML is missing.")
    print("Please run: pip install PyYAML")
    sys.exit(1)

CONFIG_FILE = "config.yml"

# Colors
RESET = "\033[0m"
BOLD = "\033[1m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def is_valid_ip(ip):
    parts = ip.split('.')
    if len(parts) != 4: return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False

def print_header():
    clear_screen()
    print(f"{BLUE}{BOLD}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║          🛡️  RemnaGuard DNS Wizard (v2.0)            ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"{RESET}")
    print(f"{CYAN}Manage your Domain -> Zone -> IP mappings interactively.{RESET}")
    print(f"{CYAN}Configuration File: {CONFIG_FILE}{RESET}\n")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"domains": []}
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict): data = {}
            if "domains" not in data or data["domains"] is None:
                data["domains"] = []
            return data
    except Exception as e:
        print(f"{RED}Error loading config: {e}{RESET}")
        return {"domains": []}

def save_config(config):
    try:
        if os.path.exists(CONFIG_FILE):
            shutil.copy(CONFIG_FILE, f"{CONFIG_FILE}.bak")
        
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"\n{GREEN}✅ Configuration saved to {CONFIG_FILE}!{RESET}")
        time.sleep(1)
    except Exception as e:
        print(f"\n{RED}❌ Failed to save config: {e}{RESET}")
        input("Press Enter to continue...")

def input_clean(prompt, default=None):
    d_str = f" [{default}]" if default else ""
    val = input(f"{YELLOW}{prompt}{d_str}: {RESET}").strip()
    if not val and default:
        return default
    return val

def manage_ips(current_ips):
    ips = list(current_ips)
    while True:
        print(f"\nCurrent IPs: {GREEN}{', '.join(ips) if ips else '(none)'}{RESET}")
        print("1. Add IP")
        print("2. Remove IP")
        print("3. Done")
        
        choice = input(f"{YELLOW}Select option: {RESET}")
        if choice == '1':
            new_ip = input_clean("Enter IP address")
            if new_ip:
                if is_valid_ip(new_ip):
                    if new_ip not in ips:
                        ips.append(new_ip)
                else:
                    print(f"{RED}❌ Invalid IP format!{RESET}")
                    time.sleep(1)
        elif choice == '2':
            to_remove = input_clean("Enter IP to remove")
            if to_remove in ips:
                ips.remove(to_remove)
        elif choice == '3':
            break
    return ips

def main():
    config = load_config()
    if "domains" not in config: config["domains"] = []
    
    while True:
        print_header()
        print(f"{BOLD}Current Configuration:{RESET}")
        if not config["domains"]:
            print("  (Empty)")
        else:
            for i, d in enumerate(config["domains"]):
                print(f"{i+1}. {BOLD}{d.get('domain')}{RESET}")
                for z in d.get("zones", []):
                    ips_str = ", ".join(z.get('ips', []))
                    print(f"   • {CYAN}{z.get('name')}{RESET} -> {ips_str}")
        
        print(f"\n{BOLD}Menu:{RESET}")
        print("1. Add/Edit Domain")
        print("2. Delete Domain")
        print("3. Save & Exit")
        print("4. Exit Without Saving")
        
        choice = input(f"\n{YELLOW}Select option: {RESET}")
        
        if choice == '1':
            domain_name = input_clean("Enter Domain (e.g. example.com)")
            domain = next((d for d in config["domains"] if d["domain"] == domain_name), None)
            if not domain:
                domain = {"domain": domain_name, "zones": []}
                config["domains"].append(domain)
            
            zone_name = input_clean("Enter Zone Name (@ or subdomain)", default="@")
            zone = next((z for z in domain["zones"] if z["name"] == zone_name), None)
            if not zone:
                zone = {"name": zone_name, "ips": [], "proxied": False, "ttl": 1}
                domain["zones"].append(zone)
            
            zone["ips"] = manage_ips(zone["ips"])
            proxied = input_clean("Cloudflare Proxy? (y/n)", default="y" if zone["proxied"] else "n")
            zone["proxied"] = True if proxied.lower() == 'y' else False
            
        elif choice == '2':
            if not config["domains"]: continue
            idx = int(input_clean("Enter domain number to delete") or 0) - 1
            if 0 <= idx < len(config["domains"]):
                del config["domains"][idx]
                
        elif choice == '3':
            save_config(config)
            break
        elif choice == '4':
            print("Changes discarded.")
            break

if __name__ == "__main__":
    main()
