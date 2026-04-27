import requests
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========================================================
# Set these as environment variables:
#   export APPS_SCRIPT_URL="https://script.google.com/macros/s/YOUR_ID/exec"
#   export APPS_SCRIPT_API_KEY="your_strong_secret_key"
# ========================================================
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "")
API_KEY = os.environ.get("APPS_SCRIPT_API_KEY", "")

# ==================== CACHE ====================
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600       # 10 min hard expiry
CACHE_STALE = 30      # After 30s, data is "stale" but still served while refreshing
_refreshing_keys = set()  # Track keys currently being refreshed

def _get_cached(key, allow_stale=True):
    """Get cached data. If allow_stale=True, returns stale data and triggers background refresh."""
    with _cache_lock:
        if key in _cache:
            data, ts = _cache[key]
            age = time.time() - ts
            if age < CACHE_STALE:
                return data  # Fresh
            if allow_stale:
                # Stale but usable — trigger background refresh if not already running
                if key not in _refreshing_keys:
                    _refreshing_keys.add(key)
                    threading.Thread(target=_bg_refresh_key, args=(key,), daemon=True).start()
                return data  # Return stale data immediately
            # Not allowing stale and data is old — treat as miss
            if age >= CACHE_TTL:
                del _cache[key]
    return None

def _bg_refresh_key(key):
    """Background refresh a single cache key."""
    try:
        if key.startswith("alldata_"):
            file_name = key[len("alldata_"):]
            _fetch_and_cache("getAllChitData", file_name, key)
        elif key.startswith("viewdata_"):
            file_name = key[len("viewdata_"):]
            _fetch_and_cache("getChitViewData", file_name, key)
        elif key == "chit_folders":
            resp = requests.get(_get_url(), params=_params("getChitFolders"), timeout=30)
            _set_cache(key, resp.json())
        elif key.startswith("chit_files_"):
            folder = key[len("chit_files_"):]
            p = _params("getChitFiles")
            if folder:
                p["folder"] = folder
            resp = requests.get(_get_url(), params=p, timeout=30)
            _set_cache(key, resp.json())
    except Exception:
        pass
    finally:
        with _cache_lock:
            _refreshing_keys.discard(key)

def _fetch_and_cache(action, file_name, cache_key):
    """Fetch from Apps Script and store in cache."""
    resp = requests.get(_get_url(), params=_params(action, file=file_name), timeout=30)
    data = resp.json()
    _set_cache(cache_key, data)
    return data

def _set_cache(key, data):
    with _cache_lock:
        _cache[key] = (data, time.time())

def clear_cache(file=None):
    """Clear cache for a specific file or all."""
    with _cache_lock:
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

def add_user(username, password, role, email="", chit_file=""):
    if find_user(username):
        return False, "User already exists"
    clear_cache("users")
    resp = requests.post(_get_url(), params=_params("addUser"),
                         json={"username": username, "password": password, "role": role, "email": email, "chitFile": chit_file}, timeout=30)
    return True, "User added"

def delete_user(username):
    clear_cache("users")
    resp = requests.post(_get_url(), params=_params("deleteUser"),
                         json={"username": username}, timeout=30)
    return True, "Deleted"

def update_user(username, password=None, role=None, email=None, chit_file=None):
    clear_cache("users")
    resp = requests.post(_get_url(), params=_params("updateUser"),
                         json={"username": username, "password": password or "", "role": role or "", "email": email if email is not None else "", "chitFile": chit_file if chit_file is not None else ""}, timeout=30)
    return True, "Updated"

# ==================== CHIT FILE OPERATIONS ====================

def get_chit_folders():
    """Get list of subfolder names from the chitData folder."""
    cached = _get_cached("chit_folders")
    if cached is not None:
        return cached
    resp = requests.get(_get_url(), params=_params("getChitFolders"), timeout=30)
    data = resp.json()
    _set_cache("chit_folders", data)
    return data

def get_chit_files(folder_name=None):
    """Get list of spreadsheet names from a folder inside chitData."""
    cache_key = f"chit_files_{folder_name}" if folder_name else "chit_files"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached
    params = _params("getChitFiles")
    if folder_name:
        params["folder"] = folder_name
    resp = requests.get(_get_url(), params=params, timeout=30)
    data = resp.json()
    _set_cache(cache_key, data)
    return data

def get_all_chit_data(spreadsheet_name, force_refresh=False):
    """Get ALL data for a chit file in one API call (cached)."""
    cache_key = f"alldata_{spreadsheet_name}"
    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
    return _fetch_and_cache("getAllChitData", spreadsheet_name, cache_key)

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
        "contactNumber": data.get("contactNumber", ""),
        "conducted": data.get("conducted", ""),
        "balanceChit": data.get("balanceChit", "")
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

def get_chit_view_data(spreadsheet_name, force_refresh=False):
    """Get full view data: chitDetails sheet, all chitNumberDetails rows, and all members."""
    cache_key = f"viewdata_{spreadsheet_name}"
    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
    return _fetch_and_cache("getChitViewData", spreadsheet_name, cache_key)

# ==================== PARALLEL BACKGROUND REFRESH ====================

def refresh_all_files():
    """Refresh all chit files in parallel using thread pool."""
    try:
        folders = get_chit_folders()
        all_files = []
        for folder in folders:
            files = get_chit_files(folder)
            all_files.extend(files)

        if not all_files:
            return

        # Use thread pool to refresh files in parallel (max 4 concurrent)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for f in all_files:
                futures.append(executor.submit(_refresh_single_file, f))
            # Wait for all to complete (with timeout)
            for future in as_completed(futures, timeout=120):
                try:
                    future.result()
                except Exception:
                    pass
    except Exception:
        pass

def _refresh_single_file(file_name):
    """Refresh both cache entries for a single file."""
    try:
        _fetch_and_cache("getAllChitData", file_name, f"alldata_{file_name}")
    except Exception:
        pass
    try:
        _fetch_and_cache("getChitViewData", file_name, f"viewdata_{file_name}")
    except Exception:
        pass
