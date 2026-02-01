# 🛡️ RemnaGuard

**Autonomous AI Sentinel for Remnawave Clusters.**

RemnaGuard is a high-performance monitoring bot designed to protect Remnawave (Xray/V2Ray) clusters from GFW probing, traffic throttling, and performance degradation. It integrates **Gemini AI** for intelligent baseline analysis and anomaly verification.

---

## 🚀 Features

### 📊 Real-Time Monitoring
- **Deep Node Inspection**: Tracks Speed, Users, Efficiency (KB/s per user) every 30 seconds.
- **Sparkline Graphs**: Visual 6-hour efficiency trends directly in Telegram.
- **Top Nodes**: Live leaderboard of busiest servers.

### 🧠 AI-Powered Analysis (Gemini)
- **Smart Baselines**: AI analyzes 24h history to set dynamic thresholds 4 times/day.
- **Anti-False-Positive**: Intelligent verification of "suspicious" behavior before alerting.
- **On-Demand Analysis**: Ask Gemini to analyze a specific node's performance trend.
- **Multi-Model Support**: Switch between `gemini-pro`, `gemini-1.5-flash`, etc.

### 🛡️ Autonomous Defense
- **Zero Throughput Detection**: Identifies "zombie" nodes that appear online but move no traffic.
- **Efficiency Throttling**: Detects GFW throttling patterns (high users, low speed).
- **Silent Logging**: Records "SUSPICIOUS" events that don't trigger alerts for later analysis.

### 📈 Analytics & Exports
- **Daily Digest**: Midnight summary of peak users, incidents, and cluster efficiency.
- **Uptime Reports**: 7-day availability tracking.
- **Database Export**: Download your full SQLite history for external analysis.

---

## 🛠️ Installation

### Quick Start
```bash
git clone https://github.com/YourRepo/RemnaGuard.git
cd RemnaGuard
./install.sh
```

### Configuration
The installer will prompt you for:
- **Remnawave URL/Token**: For API access.
- **Telegram Bot Token**: For notifications.
- **Gemini API Key**: For AI features (Optional but recommended).

---

## 🤖 Bot Commands

| Command | Description |
|:---|:---|
| **/start** | Open the interactive dashboard menu |
| **/status** | View system health and API connectivity |
| **/nodes** | List all monitored nodes and their status |
| **/top** | Show top 5 busiest nodes |
| **/graph** | View 6-hour efficiency sparklines |
| **/node [name]** | Detailed stats and AI analysis for a node |
| **/uptime** | 7-Day uptime percentages |
| **/digest** | View today's cluster performance summary |
| **/alerts** | View recent 10 alerts |
| **/reports** | View history of silent/resolved incidents |
| **/config** | Interactive threshold editor |
| **/export** | 📦 Download the `remnaguard.db` database file |
| **/analyze [name]** | 🧠 Ask AI to analyze a specific node's history |
| **/ai_model** | 🧠 Switch Gemini models (Pro/Flash/etc) |

---

## 🐳 Docker Management

**Restarting** (Updates code changes):
```bash
docker compose restart remnaguard
```

**Viewing Logs**:
```bash
docker compose logs -f remnaguard
```

**Rebuilding** (Updates dependencies):
```bash
./install.sh
# Check "Force Rebuild" if prompted
```

---

## 📝 License
MIT License. Built for the Remnawave Community.
