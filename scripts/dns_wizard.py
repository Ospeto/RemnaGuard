import json
import os
import sys

# --- ANSI Colors ---
BLUE = '\033[94m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

CONFIG_FILE = 'config/dns_mapping.json'

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data
        except Exception:
            return {}
    return {}

def save_config(data):
    if not os.path.exists('config'):
        os.makedirs('config')
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"\n{GREEN}✅ Configuration saved successfully!{RESET}")
    input(f"{DIM}Press Enter to continue...{RESET}")

def print_banner():
    clear_screen()
    print(f"{BLUE}{BOLD}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║             🛡️  RemnaGuard DNS Wizard                    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{RESET}")
    print(f"{DIM}Use this tool to map your Remnawave Nodes to Cloudflare Domains.{RESET}")
    print(f"{DIM}When a node is throttled, RemnaGuard will manage these DNS records.{RESET}\n")

def get_input(prompt, default=None):
    if default:
        user_in = input(f"{prompt} [{default}]: ").strip()
        return user_in if user_in else default
    return input(f"{prompt}: ").strip()

def edit_mapping(mappings, node_name=None):
    print_banner()
    print(f"{BOLD}✏️  Edit Mapping{RESET}\n")
    
    if not node_name:
        print(f"{YELLOW}Type the exact name of the node as it appears in your RemnaGuard panel.{RESET}")
        node_name = get_input("Node Name (e.g. US-Node-1)")
        if not node_name: return

    current = mappings.get(node_name, {})
    
    print(f"\n{BLUE}Configuring '{node_name}'...{RESET}")
    print(f"{DIM}Enter the domain name that points to this node's IP.{RESET}")
    domain = get_input("DNS Domain (e.g. vpn.example.com)", current.get('domain'))
    
    print(f"\n{DIM}Should Cloudflare proxy traffic? (Orange Cloud){RESET}")
    print(f"{DIM}- 'y' = Hidden IP (Better security, might affect speed){RESET}")
    print(f"{DIM}- 'n' = Direct IP (Faster, reveals IP){RESET}")
    is_proxied = current.get('proxied', False)
    proxied_in = get_input("Enable Proxy? (y/n)", "y" if is_proxied else "n").lower()
    proxied = proxied_in.startswith('y')
    
    mappings[node_name] = {"domain": domain, "proxied": proxied}
    print(f"\n{GREEN}✅ Updated mapping for {node_name}!{RESET}")
    time.sleep(1)

def main():
    import time
    mappings = load_config()
    # Remove metadata for display
    comment = mappings.pop("_comment", "RemnaGuard DNS Config")

    while True:
        print_banner()
        
        # List Mappings
        print(f"{BOLD}Current Configuration:{RESET}")
        nodes = [k for k in mappings.keys() if not k.startswith("_")]
        
        if not nodes:
            print(f"  {YELLOW}No nodes configured yet.{RESET}")
        else:
            print(f"  {DIM}{'#':<3} {'Node Name':<20} {'Cloudflare Domain':<30} {'Proxy'}{RESET}")
            print(f"  {DIM}{'-'*65}{RESET}")
            for i, node in enumerate(nodes, 1):
                conf = mappings[node]
                proxy_status = f"{YELLOW}☁️ Proxied{RESET}" if conf.get('proxied') else f"{DIM}⚪ Direct{RESET}"
                print(f"  {BOLD}{i:<3}{RESET} {node:<20} {conf.get('domain'):<30} {proxy_status}")

        print(f"\n{BOLD}Actions:{RESET}")
        print(f"  [{GREEN}1{RESET}] Add New Mapping")
        print(f"  [{BLUE}2{RESET}] Edit Existing Mapping")
        print(f"  [{RED}3{RESET}] Delete Mapping")
        print(f"  [{YELLOW}S{RESET}] Save & Exit")
        print(f"  [{DIM}Q{RESET}] Quit (Discard Changes)")
        
        choice = get_input("\nSelect an option").lower()
        
        if choice == '1':
            edit_mapping(mappings)
        elif choice == '2':
            if not nodes:
                print(f"\n{RED}No mappings to edit!{RESET}")
                time.sleep(1)
                continue
            idx = get_input(f"Enter number (1-{len(nodes)})")
            try:
                node_name = nodes[int(idx)-1]
                edit_mapping(mappings, node_name)
            except (ValueError, IndexError):
                print(f"\n{RED}Invalid number.{RESET}")
                time.sleep(1)
        elif choice == '3':
             if not nodes:
                continue
             idx = get_input(f"Enter number to delete (1-{len(nodes)})")
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
