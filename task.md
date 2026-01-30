# Comprehensive Detection Upgrade

- [x] **Probe Defense**: Implement "Invalid Request Version" burst detection (3-5 hits in <60s).
- [x] **Smart Auth**: Cross-reference `AUTH_FAIL` with active users to reduce false positives.
- [-] **Throttling Math**: Refine `ThrottlingCalculator` to use MVT (Minimum Viable Throughput) logic.
- [x] **API Stats**: Implement `get_nodes()` in `RemnawaveClient` to fetch traffic stats.
- [x] **Precision Monitoring**: Update `ThrottlingCalculator` to use API stats instead of `psutil`.
- [x] **Long-Term Monitoring**: Implement 5-hour rolling average for efficiency checks.
- [x] **3-Stage Alerts**: Implement 1h/3h/5h verification steps to strict alert filtering.
- [x] **Bot Cleanup**: Remove real-time speed display from `/nodes`.
- [/] Implement Interactive Config UI
    - [x] Design Button Layout
    - [ ] Implement Callback Handlers
    - [ ] Add Presets for Thresholds
- [/] Verification
    - [ ] Verify Speed Display (Smoothed)
    - [ ] Verify Config Buttons
- [ ] **Playbooks**: Add `block_ip` or `rotate_port` suggestions to alerts (Metadata).
- [ ] **Validation**: Verify new algorithms with mock data.

# Cleanup & Optimization
# Cleanup & Optimization
- [x] **Remove Legacy Code**: Delete `parser.py`, `docker_reader.py`, and `AnomalyDetector` (Log Analysis).
- [x] **Optimize Client**: shared `httpx.Client` session in `RemnawaveClient` for efficiency.
- [x] **Simplify Config**: Remove volume mounts from `docker-compose` and "Local Mode" from `install.sh`.
- [x] **Documentation**: Rewrite `README.md` with "Centralized Architecture" and "MVT Formula" details.

# Final Polish
- [x] **Code**: Remove `BOT_MODE` from `main.py` (Always Poll).
- [x] **Config**: Remove `BOT_MODE` from `install.sh` and `docker-compose.yml`.
- [x] **Docs**: Rename "Master Node" to "Monitor Instance" in `README.md`.

# Feature Requests
- [x] **Bot**: Add `/nodes` command to list cluster health/status.
- [x] **Reliability**: Enhance Telegram alerts (Retries + Rate Limit) and prevent spam (Cooldowns).

# Bot Enhancements
- [ ] **Command**: `/alerts` - Replay recent alert history (Last 10).
- [ ] **Command**: `/config` - View current detection thresholds (Read-Only).
- [ ] **Command**: `/top` - List top 5 nodes by traffic/users.

# Debugging & Cleanup
- [x] **API**: Debug "No nodes found" error (Log raw response).
- [x] **Bot**: Remove `/ban` and `/speedtest` commands (Focus on monitoring).
