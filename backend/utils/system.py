import psutil


def get_system_info() -> dict:
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    disk_usage = psutil.disk_usage("/")
    swap = psutil.swap_memory()
    return {
        "total_memory": memory.total,
        "used_memory": memory.used,
        "cpu_percent": cpu_percent,
        "cpu_cores": psutil.cpu_count() or 0,
        "disk_total": disk_usage.total,
        "disk_used": disk_usage.used,
        "swap_total": swap.total,
        "swap_used": swap.used,
    }
