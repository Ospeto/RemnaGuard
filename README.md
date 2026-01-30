# 🛡️ RemnaGuard

**RemnaGuard** is a centralized, intelligent monitoring companion for **Remnawave**. It protects your cluster from Great Firewall (GFW) throttling by analyzing traffic patterns and detecting "Chronic Congestion" before it affects your users.

Unlike basic monitors that spam you with "Speed = 0" alerts every time a user pauses a video, RemnaGuard uses an **Incident State Machine** to verify anomalies before alerting.

🔗 **Repository**: [https://github.com/Ospeto/RemnaGuard](https://github.com/Ospeto/RemnaGuard)

---

## 🧠 How It Works (Logic V2)

RemnaGuard is built on the philosophy of **"Silence is Golden, but Logs are Diamond"**. It avoids alerting on minor fluctuations but maintains a strict watch on potential threats.

### 1. The Incident State Machine 🚦
Instead of alerting instantly, RemnaGuard tracks suspicious events through a lifecycle:

1.  **🟢 Healthy**: Normal operation.
2.  **🟡 Suspicious (Log Mode)**: 
    *   **Trigger**: Speed drops below threshold (e.g., < 20 KB/s/user).
    *   **Action**: An "Incident" is recorded internally. **No Alert is sent.**
3.  **🟠 Verifying**: 
    *   **Logic**: The system watches the node for ~1-5 minutes.
    *   **Auto-Resolve**: If performance recovers, the incident is closed silently. You can view these in `/reports`.
    *   **Escalate**: If performance remains bad, it moves to **Confirmed**.
4.  **🔴 Confirmed (Alert)**: 
    *   **Action**: A notification is sent to Telegram immediately.

### 2. GFW Fast Track (The "Red Line") 🚨
Some threats require immediate action. If RemnaGuard detects a **GFW Signature**, it bypasses the proper verification steps and alerts **instantly**.

> **Signature**: Active Users > 3 **AND** Speed near Zero (< 10 KB/s)
> **Result**: `🚨 GFW LOCK DETECTED` (Critical Alert)

---

## 🤖 Bot Commands

RemnaGuard lives in your Telegram group.

| Command | Description |
| :--- | :--- |
| `/status` | **System Health**: Checks connection to Remnawave API and Bot host stats (CPU/RAM). |
| `/nodes` | **Cluster Overview**: Lists all nodes, their status (Online/Offline), and Active Users. |
| `/top` | **Top Nodes**: Lists the top 5 busiest nodes by active user count. |
| `/alerts` | **Alert History**: Shows the last 10 CRITICAL/WARNING alerts. |
| `/reports` | **Silent Incidents**: *[NEW]* Shows incidents that were detected but Auto-Resolved without bothering you. |
| `/config` | **Settings**: Change detection thresholds (Min Users, Min Speed, Efficiency) on the fly. |

---

## ⚙️ Configuration

You can tune the sensitivity via `.env` or the `/config` command.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `THROTTLE_MIN_USERS` | `3` | Minimum active users required to start monitoring a node. (Ignores empty nodes). |
| `THROTTLE_SPEED_LIMIT`| `50` | Total bandwidth floor (KB/s). Below this is suspicious. |
| `THROTTLE_PER_USER` | `20` | Minimum acceptable speed per user (KB/s). |

---

## 🚀 Installation

### Prerequisites
- Docker & Docker Compose
- A Telegram Bot Token (from @BotFather)
- Remnawave Panel URL & Admin Token

### Quick Start
1. **Clone the Repo**
   ```bash
   git clone https://github.com/Ospeto/RemnaGuard.git
   cd RemnaGuard
   ```

2. **Configure**
   ```bash
   # Run the installer
   chmod +x install.sh
   ./install.sh
   ```
   *The installer will guide you through setting up your tokens and deploying the container.*

3. **Updating**
   ```bash
   git pull
   ./install.sh
   ```

---

## 📂 Architecture

- **`src/main.py`**: Entry point. Manages the AsyncIO Loop.
- **`src/bot/`**: Telegram Bot logic (Aiogram). Handles user commands.
- **`src/engine/logic.py`**: The "Brain". Implements the **Incident State Machine** and GFW signature detection.
- **`src/services/`**: 
  - `remnawave.py`: Robust HTTP client for the Panel API (with JSON error handling).
  - `monitor.py`: System resource monitoring.
