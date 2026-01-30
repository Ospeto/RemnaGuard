# Implementation Plan: Advanced GFW Detection

## Goal
Make detection logic robust against "noisy neighbors" and "idle users" to reduce false positives/negatives.

## 1. Configurable MVT (Minimum Viable Throughput)
Hardcoded values are bad. We will move them to `.env`:
- `THROTTLE_MIN_USERS` (Default: 3)
- `THROTTLE_SPEED_LIMIT` (Default: 50 KB/s - Increased from 30)

## 2. "Per-User" Efficiency Formula
Instead of just "Total Speed", we check **Avg Speed Per User**.
- *Formula*: `Velocity / UserCount`
- *Trigger*: If `AvgSpeed < 10KB/s` (Dial-up speeds).
- *Benefit*: Scales for 100 users. (100 users doing 1MB/s is still slow!)

## 3. Multi-Stage Verification (3-Step Plan)
Avoids false positives by verifying persistence over time.
- **Stage 1 (1 Hour)**: Check 1h Rolling Average.
- **Stage 2 (3 Hours)**: Check 3h Rolling Average.
- **Stage 3 (5 Hours)**: Check 5h Rolling Average.

**Alert Logic**:
- **Trigger**: IF (Avg@5h < Limit) AND (Avg@3h < Limit) AND (Avg@1h < Limit).
- **Recovery**: IF (Avg@1h > Limit) -> **NO ALERT** (Improving).
- *Benefit*: Ignores temporary dips. Only alerts if the node is *consistently* and *chronically* slow.

# Bot Commandments (Proposed)

## 1. `/config`
Admins need to know *why* alerts are firing.
- **Output**:
  ```
  ⚙️ Detection Config:
  • Min Users  : 3
  • Min Speed  : 50 KB/s
  • Efficiency : 10 KB/s/user
  • Interval   : 30s
  ```

## 2. `/alerts`
"What did I miss?" - Shows the last 5-10 alerts stored in memory.
- **Output**:
  ```
  🔔 Recent Alerts:
  1. [14:05] 🐌 Congestion: US-Node (8KB/s/user)
  2. [13:50] 💀 Zombie: TH-Node (0 KB/s)
  ```

## 3. `/top`
"Who is hogging resources?"
- **Output**: Sorted list of nodes by Active Users.

