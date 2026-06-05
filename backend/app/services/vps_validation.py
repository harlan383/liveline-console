import ipaddress


def validate_public_ipv4(host: str) -> str | None:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "INVALID_VPS_HOST"

    if ip.version != 4 or not ip.is_global:
        return "INVALID_VPS_HOST"

    return None


def validate_ssh_port(port: int) -> str | None:
    if port < 1 or port > 65535:
        return "INVALID_VPS_HOST"
    return None
