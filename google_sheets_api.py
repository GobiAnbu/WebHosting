import requests
import os
import time

# ========================================================
# Set these as environment variables:
#   export APPS_SCRIPT_URL="https://script.google.com/macros/s/YOUR_ID/exec"
#   export APPS_SCRIPT_API_KEY="your_strong_secret_key"
# ========================================================
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "")
API_KEY = os.environ.get("APPS_SCRIPT_API_KEY", "")

# ==================== CACHE ====================
# Cache - background thread refreshes every 10 seconds
_cache = {}
CACHE_TTL = 600  # 10 minutes fallback (background thread refreshes every 10 sec)

def _get_cached(key):
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None

def _set_cache(key, data):
    _cache[key] = (data, time.time())

def clear_cache(file=None):
    """Clear cache for a specific file or all."""
    if file:
        keys_to_del = [k for k in _cache if file in k]
        for k in keys_to_del:
            del _cache[k]
    else:
        _cache.clear()

def _get_url():
    if not APPS_SCRIPT_URL:
        raise Exception("Apps Script URL not configured. Set APPS_SCRIPT_URL in google_sheets_api.py")
    return APPS_SCRIPT_URL

def _params(action, **kwargs):
    """Build query params with API key included."""
    p = {"action": action, "key": API_KEY}
    p.update(kwargs)
    return p

# ==================== USER OPERATIONS ====================

def get_all_users():
    cached = _get_cached("users")
    if cached is not None:
        return cached
    resp = requests.get(_get_url(), params=_params("getUsers"), timeout=30)
    data = resp.json()
    _set_cache("users", data)
    return data

def find_user(username):
    for u in get_all_users():
        if u["username"] == username:
            return u
    return None

def add_user(username, password, role, email=""):
    if find_user(username):
        return False, "User already exists"
    clear_cache("users")
    resp = requests.post(_get_url(), params=_params("addUser"),
                         json={"username": username, "password": password, "role": role, "email": email}, timeout=30)
    return True, "User added"

def delete_user(username):
    clear_cache("users")
    resp = requests.post(_get_url(), params=_params("deleteUser"),
                         json={"username": username}, timeout=30)
    return True, "Deleted"

def update_user(username, password=None, role=None, email=None):
    clear_cache("users")
    resp = requests.post(_get_url(), params=_params("updateUser"),
                         json={"username": username, "password": password or "", "role": role or "", "email": email if email is not None else ""}, timeout=30)
    return True, "Updated"

# ==================== CHIT FILE OPERATIONS ====================

def get_chit_files():
    """Get list of spreadsheet names from the chitData folder."""
    cached = _get_cached("chit_files")
    if cached is not None:
        return cached
    resp = requests.get(_get_url(), params=_params("getChitFiles"), timeout=30)
    data = resp.json()
    _set_cache("chit_files", data)
    return data

def get_all_chit_data(spreadsheet_name, force_refresh=False):
    """Get ALL data for a chit file in one API call (cached)."""
    cache_key = f"alldata_{spreadsheet_name}"
    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
    resp = requests.get(_get_url(), params=_params("getAllChitData", file=spreadsheet_name), timeout=30)
    data = resp.json()
    _set_cache(cache_key, data)
    return data

def get_members(spreadsheet_name):
    """Get members who haven't withdrawn — uses batch endpoint."""
    data = get_all_chit_data(spreadsheet_name)
    return data.get("activeMembers", [])

def get_all_members(spreadsheet_name):
    """Get all members — uses batch endpoint."""
    data = get_all_chit_data(spreadsheet_name)
    return data.get("members", [])

def get_chit_number(spreadsheet_name):
    """Get chit number details — uses batch endpoint."""
    data = get_all_chit_data(spreadsheet_name)
    return {
        "chitNumber": data.get("chitNumber", ""),
        "chitRemaining": data.get("chitRemaining", 0),
        "amountPerPerson": data.get("amountPerPerson", 0),
        "totalAmount": data.get("totalAmount", 0),
        "chitName": data.get("chitName", ""),
        "gpay": data.get("gpay", ""),
        "contactNumber": data.get("contactNumber", "")
    }

def get_reminder_data(spreadsheet_name):
    """Get amount per person and gpay — uses batch endpoint."""
    data = get_all_chit_data(spreadsheet_name)
    return {
        "amountPerPerson": data.get("amountPerPerson", "0"),
        "gpay": data.get("gpay", "")
    }

def get_contact_number(spreadsheet_name):
    """Get contact number — uses batch endpoint."""
    data = get_all_chit_data(spreadsheet_name)
    return {"contactNumber": data.get("contactNumber", "")}

def update_campaign(spreadsheet_name, name, chit_amount, discount_amount, amount_need_to_pay):
    """Update chitNumberDetails and chitMembers after a campaign."""
    clear_cache(spreadsheet_name)  # Clear cache since data is changing
    resp = requests.post(_get_url(), params=_params("updateCampaign", file=spreadsheet_name),
                         json={
                             "name": name,
                             "chitAmount": chit_amount,
                             "discountAmount": discount_amount,
                             "amountNeedToPay": amount_need_to_pay
                         }, timeout=30)
    return resp.json()

