# Skill: System Diagnosis
This skill provides a methodical procedure for analyzing the health and status of the host system.

## Procedure
1. **Check System Uptime**: Run `uptime` to see how long the system has been running.
2. **Resource Monitoring**:
   - Memory: Run `free -h`.
   - CPU/Processes: Run `top -b -n 1 | head -n 20`.
3. **Disk Usage**: Run `df -h` to check for low disk space on all mounted partitions.
4. **Network Status**: Run `ip addr` or `ifconfig` to check active interfaces.
5. **Log Analysis**: Check the last 20 lines of system logs if accessible (e.g., `tail -n 20 /var/log/syslog`).

## Expected Outcome
A comprehensive report summarizing the current system load, resource availability, and any immediate warnings (e.g., high memory usage or full disks).
