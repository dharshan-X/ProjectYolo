# Skill: System Diagnosis

A methodical procedure for analyzing the health and status of the host system. Designed to be **portable** across Linux/macOS and produce a **structured, thresholded** report.

---

## Core Principles

- **Read-only by default**: Collect diagnostics without mutating the system. Do not restart services or kill processes unless the user has explicitly approved.
- **Threshold-driven**: Every metric is reported with a verdict against realistic thresholds (see table below). Numbers without verdicts are noise.
- **Platform-aware**: Detect the host OS first; choose the correct tool variants (e.g., `vm_stat` on macOS, `free` on Linux).
- **Bounded scope**: This skill reports on state. It does not fix problems. When a fix is required, hand off to a remediation task explicitly.

---

## Procedure

### 1. Identify the Platform
Run `uname -a` (Unix) or `ver` (Windows). Branch the rest of the procedure on the result.

### 2. Uptime & Load
- **Linux/macOS**: `uptime` → gives load average (1, 5, 15 min).
- **Windows**: `systeminfo | findstr /C:"System Up Time"`.

### 3. Memory
- **Linux**: `free -h` → total, used, free, available, swap.
- **macOS**: `vm_stat` plus `sysctl hw.memsize`.
- **Windows**: `wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /VALUE`.

Pay attention to **available** memory, not just free — Linux reclaims page cache. Watch swap activity.

### 4. CPU & Top Processes
- **Linux**: `top -b -n 1 | head -n 20` (or `ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -n 15` for portability).
- **macOS**: `ps -arcwwwxo "pid %cpu %mem command" | head -n 15`.
- **Windows**: `tasklist /v | head -n 20` or `Get-Process | Sort-Object CPU -Descending | Select-Object -First 15`.

Flag any process consuming >80% of a core persistently; one-shot spikes are usually benign.

### 5. Disk Usage
- **All platforms**: `df -h` (or `Get-PSDrive -PSProvider FileSystem`).
- Inspect every mounted partition. Check inodes on Linux with `df -i` if disk usage is low but writes fail.
- Mount-spaces near 100% cause cascading write failures across the whole system.

### 6. Network
- **Linux**: `ip -br addr` and `ss -tulpn` (or `netstat -tulpn` if `ss` is unavailable).
- **macOS**: `ifconfig` and `netstat -an | grep LISTEN`.
- **Windows**: `ipconfig /all` and `netstat -an | findstr LISTENING`.

Confirm the interfaces you expect to be up are actually up, and that no unexpected listeners are exposed.

### 7. Logs & Recent Events
- **Linux**: `tail -n 50 /var/log/syslog` (Debian/Ubuntu) or `/var/log/messages` (RHEL/CentOS). On systemd hosts: `journalctl -n 50 --no-pager`.
- **macOS**: `log show --last 1h --predicate 'eventType == logEvent' --style compact`.
- **Windows**: `Get-EventLog -LogName System -Newest 50`.

Filter for `error`, `fail`, `oom`, `panic`, `segfault`. Adjust grep to your platform's idioms.

### 8. Targeted Checks (when warranted)
- **Disk I/O**: `iostat -xz 1 3` (Linux, sysstat package).
- **Open files**: `lsof | wc -l` to detect file-descriptor leaks.
- **Docker**: `docker ps --format '{{.Names}}: {{.Status}}'`.
- **Containers / systemd units**: `systemctl list-units --state=failed`.

Add only the checks that are relevant to the user's question. Don't blanket-run everything every time.

---

## Threshold Reference

Apply these verdicts when reporting:

| Metric | Healthy | Caution | Critical |
|---|---|---|---|
| Memory utilization (used/total) | <70% | 70–90% | >90% or swap activity |
| CPU load / core count (1-min) | <1.0 | 1.0–2.0 | >2.0 |
| Disk utilization | <80% | 80–90% | >90% |
| Inode utilization (Linux) | <80% | 80–95% | >95% |
| Swap used | 0% bytes | <30% of total | >30% sustained |
| Top process CPU | varies | single transient >80% | persistent >80% |

"Cautions" deserve a sentence in the report. "Criticals" deserve a recommended next step.

---

## Structured Report Template

Render the diagnosis as a `stack` widget for scannability, followed by a short prose explanation.

```
System Health Summary — <host> at <timestamp>
─────────────────────────────────────────
Uptime:            <value>
Platform:          <os / kernel>
Load Avg (1/5/15): <values>
Memory:            used/total (avail/total) — verdict
Swap:              used/total — verdict
Disk:              / mount — verdict (per partition)
Top CPU procs:     <list>
Critical/Caution:  <bulleted list>
Log red flags:     <count + 1-line samples>
```

When handing the report off, group concerns:
- **Immediate attention**: memory >90%, disk >95%, kernels panics, failed services.
- **Watch**: load >2.0 sustained, swap creeping, top process CPU pegged.
- **Informational**: typical cycle, no anomalies.

---

## Expected Outcome

A concise, structured report summarizing current system state with thresholds applied, the most resource-intensive processes named, recent error logs flagged, and any **immediate** issues surfaced so the user can decide on remediation.

Do not auto-remediate. Diagnose, report, recommend.
