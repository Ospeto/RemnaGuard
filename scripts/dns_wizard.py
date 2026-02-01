import json
import os
import sys
import time
import shutil

# Try importing yaml, if fails, we will handle it in the wrapper script or show error
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
            return yaml.safe_load(f) or {"domains": []}
    except Exception as e:
        print(f"{RED}Error loading config: {e}{RESET}")
        return {"domains": []}

def save_config(config):
    try:
        # Create backup
        if os.path.exists(CONFIG_FILE):
            shutil.copy(CONFIG_FILE, f"{CONFIG_FILE}.bak")
        
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"\n{GREEN}✅ Configuration saved to {CONFIG_FILE}!{RESET}")
        time.sleep(1.5)
    except Exception as e:
        print(f"\n{RED}❌ Failed to save config: {e}{RESET}")
        input("Press Enter to continue...")

def input_clean(prompt, default=None):
    valid = False
    while not valid:
        d_str = f" [{default}]" if default else ""
        val = input(f"{YELLOW}{prompt}{d_str}: {RESET}").strip()
        if not val and default:
            return default
        if val:
            return val

def manage_ips(current_ips):
    print(f"\n{BOLD}Managing IPs{RESET}")
    ips = list(current_ips)
    while True:
        print(f"\nCurrent IPs: {GREEN}{', '.join(ips) if ips else '(none)'}{RESET}")
        print("1. Add IP")
        print("2. Remove IP")
        print("3. Done")
        
        choice = input(f"{YELLOW}Select option: {RESET}")
        
        if choice == '1':
            new_ip = input_clean("Enter IP address")
            if new_ip not in ips:
                ips.append(new_ip)
        elif choice == '2':
            if not ips:
                print("No IPs to remove.")
                continue
            to_remove = input_clean("Enter IP to remove")
            if to_remove in ips:
                ips.remove(to_remove)
            else:
                print(f"{RED}IP not found.{RESET}")
        elif choice == '3':
             try:
                 node_name = nodes[int(idx)-1]
                 del mappings[node_name]
                 print(f"\n{RED}🗑️  Deleted {node_name}{RESET}")
                 time.sleep(1)
             except: pass
        elif choice == 's':
            mappings["_comment"] = comment
            save_config(mappings)
            break
        elif choice == 'q':
            print("Bye!")
            sys.exit(0)

if __name__ == "__main__":
    main()
