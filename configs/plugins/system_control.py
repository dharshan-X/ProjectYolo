"""
System & OS Control Plugin for Project Yolo.
Provides tools for managing processes and network ports.
"""

import psutil

PLUGIN_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_heavy_processes",
            "description": "Lists the top processes consuming the most CPU or Memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "enum": ["cpu", "memory"],
                        "description": "Sort the processes by 'cpu' or 'memory' (default: cpu).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of processes to return (default: 5).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminates a process by its Process ID (PID).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "The Process ID to kill.",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "If true, sends SIGKILL instead of SIGTERM (default: false).",
                    },
                },
                "required": ["pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_port_in_use",
            "description": "Checks if a specific network port is currently in use and returns the process using it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {
                        "type": "integer",
                        "description": "The port number to check (e.g., 3000, 8080).",
                    }
                },
                "required": ["port"],
            },
        },
    },
]


def list_heavy_processes(sort_by: str = "cpu", limit: int = 5) -> str:
    """Lists the top processes by CPU or Memory usage."""
    try:
        processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent"]
        ):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # Sort processes
        sort_key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
        processes = sorted(
            processes, key=lambda p: p.get(sort_key, 0) or 0, reverse=True
        )

        output = [f"Top {limit} processes sorted by {sort_by.upper()}:", "-" * 40]
        for p in processes[:limit]:
            mem = p.get("memory_percent", 0)
            mem_str = f"{mem:.1f}%" if mem is not None else "N/A"
            cpu = p.get("cpu_percent", 0)
            cpu_str = f"{cpu}%" if cpu is not None else "N/A"
            output.append(
                f"PID: {p['pid']} | Name: {p['name']} | CPU: {cpu_str} | RAM: {mem_str}"
            )

        return "\n".join(output)
    except Exception as e:
        return f"Error listing processes: {e}"


def kill_process(pid: int, force: bool = False) -> str:
    """Kills a process by PID."""
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        if force:
            proc.kill()
            action = "Killed (SIGKILL)"
        else:
            proc.terminate()
            action = "Terminated (SIGTERM)"
        return f"Successfully {action} process '{name}' (PID: {pid})."
    except psutil.NoSuchProcess:
        return f"Error: No process found with PID {pid}."
    except psutil.AccessDenied:
        return f"Error: Access denied to kill PID {pid}."
    except Exception as e:
        return f"Error killing process {pid}: {e}"


def check_port_in_use(port: int) -> str:
    """Checks what process is using a specific port."""
    try:
        connections = psutil.net_connections()
        using_procs = []
        for conn in connections:
            if conn.laddr and conn.laddr.port == port:
                if conn.pid:
                    try:
                        proc = psutil.Process(conn.pid)
                        using_procs.append(
                            f"PID: {conn.pid} | Name: {proc.name()} | Status: {conn.status}"
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        using_procs.append(
                            f"PID: {conn.pid} | Status: {conn.status} (Access Denied)"
                        )
                else:
                    using_procs.append(
                        f"Status: {conn.status} (PID unknown/Access Denied)"
                    )

        if not using_procs:
            return f"Port {port} is currently free."

        # Deduplicate list
        using_procs = list(set(using_procs))
        return f"Port {port} is in use by:\n" + "\n".join(using_procs)
    except Exception as e:
        return f"Error checking port {port}: {e}"
