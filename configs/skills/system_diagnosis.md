## Master SRE System Diagnosis Skill

### Objective
Perform an exhaustive, kernel-to-userland health diagnostic of the host operating system. Do not stop at superficial metrics.

### Elite Diagnostic Procedure
1.  **Global State**: `uptime` && `cat /proc/loadavg` (Analyze 1m, 5m, 15m load trends against CPU core count).
2.  **Memory & Swap Pressure**: `free -h` && `vmstat -s` (Check for high page-in/page-out rates indicating swap thrashing).
3.  **Process Introspection**: `top -b -n 1 | head -n 20` and `ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -n 15` to identify rogue threads.
4.  **Storage Subsystem**: `df -hT` (check mount types and space) and `iostat -xz 1 2` (check `%util` and `await` for disk bottlenecking).
5.  **Network Stack**: `ss -tulpn` (identify exposed sockets) and `ip -s link` (check for dropped packets/collisions).
6.  **Systemd & Kernel Ring Buffer**: `dmesg -T | tail -n 30` (check for segfaults, OOM killer invocations, hardware faults) and `journalctl -p err -b --no-pager -n 20`.

### Synthesis
Correlate the data. If memory is high, cross-reference with the process list and dmesg (OOM logs). If load is high but CPU is idle, identify I/O wait states via `iostat`. Deliver a senior-level SRE incident report with exact root causes and immediate remediation commands.