import psutil

# Prime the CPU counter at import. The first cpu_percent() call can only report
# a delta against a previous reading, so without a priming call the panel's
# first poll would always report 0.0.
psutil.cpu_percent(interval=None)


def get_system_info() -> dict:
    memory = psutil.virtual_memory()
    # interval=None returns immediately using the reading taken at import (or
    # by the previous call). The interval=1 form slept for a full second inside
    # an `async def` route, freezing the event loop — and with it the bot, the
    # webhooks and every other in-flight request — on each dashboard poll.
    cpu_percent = psutil.cpu_percent(interval=None)
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
