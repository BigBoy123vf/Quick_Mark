import hashlib
import re
import secrets

DEVICE_COOKIE_NAME = "device_id"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year


def generate_device_token():
    return secrets.token_urlsafe(32)


def hash_device_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def device_label(user_agent_string):
    lowered_agent = (user_agent_string or "").lower()
    if "iphone" in lowered_agent:
        return "iPhone"
    if "ipad" in lowered_agent:
        return "iPad"
    if "android" in lowered_agent and "mobile" in lowered_agent:
        return "Android phone"
    if "android" in lowered_agent:
        return "Android tablet"
    if "macintosh" in lowered_agent or "mac os x" in lowered_agent:
        return "Mac"
    if "windows" in lowered_agent:
        return "Windows PC"
    if "linux" in lowered_agent:
        return "Linux device"
    return "Unknown device"


def operating_system(user_agent_string):
    # Best-effort OS name + version from the raw User-Agent string.
    raw_agent = user_agent_string or ""
    match = re.search(r"iPhone OS (\d+)[_.](\d+)", raw_agent) or re.search(r"CPU OS (\d+)[_.](\d+)", raw_agent)
    if match:
        return f"iOS {match.group(1)}.{match.group(2)}"
    match = re.search(r"Android (\d+(?:\.\d+)?)", raw_agent)
    if match:
        return f"Android {match.group(1)}"
    match = re.search(r"Mac OS X (\d+)[_.](\d+)", raw_agent)
    if match:
        return f"macOS {match.group(1)}.{match.group(2)}"
    if "Windows NT 10" in raw_agent:
        return "Windows 10/11"
    if "Windows" in raw_agent:
        return "Windows"
    if "Linux" in raw_agent:
        return "Linux"
    return None


def browser_name(user_agent_string):
    # Best-effort browser name + major version. Order matters: more specific first.
    raw_agent = user_agent_string or ""
    for token, label in (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser/", "Samsung Internet")):
        match = re.search(re.escape(token) + r"(\d+)", raw_agent)
        if match:
            return f"{label} {match.group(1)}"
    if "Firefox/" in raw_agent:
        match = re.search(r"Firefox/(\d+)", raw_agent)
        return f"Firefox {match.group(1)}" if match else "Firefox"
    if "Chrome/" in raw_agent:
        match = re.search(r"Chrome/(\d+)", raw_agent)
        return f"Chrome {match.group(1)}" if match else "Chrome"
    if "Version/" in raw_agent and "Safari" in raw_agent:
        match = re.search(r"Version/(\d+)", raw_agent)
        return f"Safari {match.group(1)}" if match else "Safari"
    return None
