from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from dotenv import load_dotenv
load_dotenv()
import urllib.parse
import math
import os
import json
import requests
import time
from google_sheets_api import (
    get_all_users, find_user, add_user as gs_add_user,
    delete_user as gs_delete_user, update_user as gs_update_user,
    get_chit_files as gs_get_chit_files, get_chit_folders as gs_get_chit_folders,
    get_members, get_all_members,
    get_chit_number as gs_get_chit_number, update_campaign,
    get_reminder_data, get_contact_number, get_all_chit_data,
    get_chit_view_data as gs_get_chit_view_data,
    refresh_all_files
)

import threading

from datetime import timedelta, date

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chit-fund-secret-key-2026")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

@app.before_request
def make_session_permanent():
    session.permanent = True

# ==================== BACKGROUND DATA REFRESH ====================
_bg_thread_started = False

def background_refresh():
    """Continuously refresh cache in background using parallel fetches."""
    # Initial warm-up: refresh all files immediately on startup
    refresh_all_files()
    while True:
        time.sleep(30)  # Refresh every 30 seconds (parallel makes this fast enough)
        try:
            refresh_all_files()
        except Exception:
            pass

def start_background_refresh():
    global _bg_thread_started
    if not _bg_thread_started:
        _bg_thread_started = True
        t = threading.Thread(target=background_refresh, daemon=True)
        t.start()

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"whatsapp_api_token": "", "whatsapp_phone_number_id": "", "sms_api_key": ""}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json or request.path.startswith("/get-") or request.path.startswith("/send-") or request.path.startswith("/save-"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json or request.path.startswith("/get-") or request.path.startswith("/save-") or request.path.startswith("/send-") or request.path.startswith("/add-") or request.path.startswith("/delete-") or request.path.startswith("/update-"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def send_whatsapp_message(phone, message):
    """Send a WhatsApp message using the WhatsApp Business Cloud API."""
    token = os.environ.get("WHATSAPP_API_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        return {"success": False, "error": "WhatsApp API not configured. Go to Settings to add your API token and Phone Number ID."}
    phone = str(phone).strip()
    if not phone.startswith("91"):
        phone = "91" + phone
    url = f"https://graph.facebook.com/v22.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        result = resp.json()
        if resp.status_code == 200 and "messages" in result:
            return {"success": True, "message_id": result["messages"][0]["id"]}
        else:
            error_obj = result.get("error", {})
            error_code = error_obj.get("code", "")
            error_subcode = error_obj.get("error_subcode", "")
            error_msg = error_obj.get("message", resp.text)

            # Provide actionable error messages for common issues
            if error_code == 200:
                detail = (
                    "WhatsApp API permission denied. This usually means: "
                    "(1) Your app is in Development mode — go to Meta App Dashboard → App Settings → Basic → toggle to Live mode. "
                    "(2) Or your access token has expired — generate a new System User token in Meta Business Settings."
                )
            elif error_code == 190:
                detail = "Access token has expired or is invalid. Go to Settings and update your WhatsApp API Token with a new one from Meta Business Suite."
            elif error_code == 131031:
                detail = f"Recipient phone number {phone} is not a valid WhatsApp number or is not opted in."
            elif error_code == 368:
                detail = "Your WhatsApp Business API has been temporarily rate limited. Please wait and try again."
            else:
                detail = f"{error_msg} (code: {error_code}, subcode: {error_subcode})" if error_code else error_msg

            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}

def send_whatsapp_interactive(phone, interactive_payload):
    """Send an interactive message (buttons/list) via WhatsApp Business API."""
    token = os.environ.get("WHATSAPP_API_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        return {"success": False, "error": "WhatsApp API not configured."}
    phone = str(phone).strip()
    if not phone.startswith("91"):
        phone = "91" + phone
    url = f"https://graph.facebook.com/v22.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": interactive_payload
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        result = resp.json()
        if resp.status_code == 200 and "messages" in result:
            return {"success": True, "message_id": result["messages"][0]["id"]}
        return {"success": False, "error": result.get("error", {}).get("message", resp.text)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _send_command_menu(phone, header_text, body_text):
    """Send the command menu as an interactive list message."""
    send_whatsapp_interactive(phone, {
        "type": "list",
        "header": {"type": "text", "text": header_text},
        "body": {"text": body_text},
        "action": {
            "button": "Select Option",
            "sections": [{
                "title": "Commands",
                "rows": [
                    {"id": "cmd_details", "title": "📋 Chit Details"},
                    {"id": "cmd_reminder", "title": "🔔 Payment Reminder"},
                    {"id": "cmd_tomorrow", "title": "📢 Chit Tomorrow"},
                    {"id": "cmd_name_search", "title": "🔍 Payment History"},
                    {"id": "cmd_change", "title": "🔄 Change Chit"},
                ]
            }]
        }
    })

def _send_chit_selection_list(phone, matched):
    """Send chit selection as an interactive list message."""
    rows = []
    for i, m in enumerate(matched):
        rows.append({
            "id": f"chit_{i}",
            "title": m["chitName"][:24]
        })
    send_whatsapp_interactive(phone, {
        "type": "list",
        "header": {"type": "text", "text": "👋 Welcome to Chit Fund Bot!"},
        "body": {"text": "You have multiple chits. Please select one:"},
        "action": {
            "button": "Select Chit",
            "sections": [{"title": "Your Chits", "rows": rows}]
        }
    })

def get_chit_file():
    """Get the chit file name from query params or JSON body."""
    if request.method == "POST":
        data = request.get_json(silent=True)
        if data and data.get("chitFile"):
            return data.get("chitFile")
    return request.args.get("chitFile", "")

def preload_all_data():
    """Preload all chit files data into cache in background."""
    try:
        folders = gs_get_chit_folders()
        for folder in folders:
            files = gs_get_chit_files(folder)
            for f in files:
                try:
                    get_all_chit_data(f)
                except Exception:
                    pass
    except Exception:
        pass

# ==================== HEALTH CHECK ====================

@app.route("/health")
def health_check():
    return jsonify({"status": "ok"}), 200

# ==================== AUTH ROUTES ====================

@app.route("/login-page")
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")

    # Try Google Sheets first, fallback to config.json
    user = None
    try:
        user = find_user(username)
    except Exception:
        pass

    if user and user.get("password") == password:
        session["logged_in"] = True
        session["username"] = username
        session["role"] = user.get("role", "user")
        session["chitFile"] = user.get("chitFile", "")
        start_background_refresh()
        return jsonify({"success": True})

    # Fallback to config.json
    cfg = load_config()
    users = cfg.get("users", {})
    if username in users and users[username].get("password") == password:
        session["logged_in"] = True
        session["username"] = username
        session["role"] = users[username].get("role", "user")
        start_background_refresh()
        return jsonify({"success": True})

    return jsonify({"success": False, "error": "Invalid username or password"})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ==================== PAGE ROUTES ====================

@app.route("/")
@login_required
def index():
    return render_template("home.html")

@app.route("/chit-details")
@login_required
def chit_details():
    return render_template("ui.html")

@app.route("/reminder")
@login_required
def reminder():
    return render_template("reminder.html")

@app.route("/chit-tomorrow")
@login_required
def chit_tomorrow():
    return render_template("chit_tomorrow.html")

@app.route("/settings")
@admin_required
def settings():
    return render_template("settings.html")

@app.route("/chit-view")
@login_required
def chit_view():
    return render_template("chit_view.html")

# ==================== CHIT DATA API ROUTES ====================

@app.route("/get-chit-files")
@login_required
def get_chit_files():
    try:
        if session.get("role") == "admin":
            # Admin sees all folders' files
            folders = gs_get_chit_folders()
            all_files = []
            for folder in folders:
                files = gs_get_chit_files(folder)
                all_files.extend(files)
            return jsonify(all_files)
        else:
            # User sees only files from their assigned folder
            user_folder = session.get("chitFile", "")
            if user_folder:
                files = gs_get_chit_files(user_folder)
                return jsonify(files)
            else:
                return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-chit-folders")
@admin_required
def get_chit_folders():
    """Return all subfolder names inside chitData - for admin dropdown."""
    try:
        folders = gs_get_chit_folders()
        return jsonify(folders)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-all-chit-files")
@admin_required
def get_all_chit_files():
    """Return all chit files from all folders - for admin."""
    try:
        folders = gs_get_chit_folders()
        all_files = []
        for folder in folders:
            files = gs_get_chit_files(folder)
            all_files.extend(files)
        print(f"[Admin] All chit files: {all_files}")
        return jsonify(all_files)
    except Exception as e:
        print(f"[Admin] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/preload-data")
@login_required
def preload_data():
    """Preload all chit data and return when done."""
    try:
        folders = gs_get_chit_folders()
        count = 0
        for folder in folders:
            files = gs_get_chit_files(folder)
            for f in files:
                try:
                    get_all_chit_data(f)
                    count += 1
                except Exception:
                    pass
        return jsonify({"success": True, "files": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/get-names")
@login_required
def get_names():
    chit_file = get_chit_file()
    try:
        members = get_members(chit_file)
        return jsonify(members)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-chit-number")
@login_required
def get_chit_number():
    chit_file = get_chit_file()
    try:
        data = gs_get_chit_number(chit_file)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-chit-view-data")
@login_required
def get_chit_view_data():
    chit_file = get_chit_file()
    try:
        data = gs_get_chit_view_data(chit_file)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/update-member-payment", methods=["POST"])
@login_required
def update_member_payment():
    data = request.get_json()
    chit_file = data.get("chitFile", "")
    member_name = data.get("memberName", "")
    month = data.get("month", "")
    status = data.get("status", "")
    if not chit_file or not member_name or not month:
        return jsonify({"error": "Missing parameters"}), 400
    try:
        from google_sheets_api import clear_cache, _refresh_single_file
        result = requests.post(
            os.environ.get("APPS_SCRIPT_URL", ""),
            params={"action": "updateMemberPayment", "key": os.environ.get("APPS_SCRIPT_API_KEY", ""), "file": chit_file},
            json={"memberName": member_name, "month": month, "status": status},
            timeout=30
        )
        resp_data = result.json()
        clear_cache(chit_file)
        # Re-fetch in background so cache is warm for next request
        threading.Thread(target=_refresh_single_file, args=(chit_file,), daemon=True).start()
        return jsonify(resp_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/send-campaign", methods=["POST"])
@login_required
def send_campaign():
    data = request.get_json()
    chit_file = data.get("chitFile", "")
    chit_amount = data.get("chitAmount", "")
    discount_amount = data.get("discountAmount", "")
    name = data.get("name", "")
    amount_need_to_pay = math.ceil((float(chit_amount) / 20) / 10) * 10 if chit_amount else 0

    # Update Google Sheet
    update_campaign(chit_file, name, chit_amount, discount_amount, amount_need_to_pay)

    # Get all members for WhatsApp links
    all_members = get_all_members(chit_file)

    chit_number = data.get("chitNumber", "")
    total_amount = data.get("totalAmount", "")
    current_date = data.get("currentDate", "")
    chit_remaining = data.get("chitRemaining", "")

    formatted_date = current_date
    if current_date:
        parts = current_date.split("-")
        if len(parts) == 3:
            formatted_date = f"{parts[2]}-{parts[1]}-{parts[0]}"

    # Get chit name
    chit_info = gs_get_chit_number(chit_file)
    chit_name = chit_info.get("chitName", "")

    msg = (
        f"Status of the Chit {chit_name}:\n\n"
        f"🎯 *Chit Taken By:* {name}\n"
        f"📌 *Chit Number:* {chit_number}\n"
        f"💰 *Total Amount:* ₹{total_amount}\n"
        f"🏷️ *Chit Amount:* ₹{chit_amount}\n"
        f"📅 *Date:* {formatted_date}\n"
        f"🔄 *Chit Remaining:* {chit_remaining}\n\n"
        f"💳 *Amount Need to Pay:* *₹{amount_need_to_pay}*\n\n"
        f"———————————\n\n"
        f"{chit_name} சிட் நிலை:\n\n"
        f"🎯 *சிட் எடுத்தவர்:* {name}\n"
        f"📌 *சிட் எண்:* {chit_number}\n"
        f"💰 *மொத்த தொகை:* ₹{total_amount}\n"
        f"🏷️ *சிட் தொகை:* ₹{chit_amount}\n"
        f"📅 *தேதி:* {formatted_date}\n"
        f"🔄 *மீதமுள்ள சிட்:* {chit_remaining}\n\n"
        f"💳 *செலுத்த வேண்டிய தொகை:* *₹{amount_need_to_pay}*\n\n"
        f"நன்றி! 🎉"
    )
    encoded = urllib.parse.quote(msg)

    # Send directly via WhatsApp API to company contact number
    chit_info_data = gs_get_chit_number(chit_file)
    contact_phone = str(chit_info_data.get("contactNumber", "")).strip()

    if contact_phone:
        result = send_whatsapp_message(contact_phone, msg)
        return jsonify(result)
    else:
        return jsonify({"success": False, "error": "No contact number found"})

@app.route("/send-reminder", methods=["POST"])
@login_required
def send_reminder():
    data = request.get_json()
    message = data.get("message", "")
    members = data.get("members", [])
    chit_file = data.get("chitFile", "")

    chit_info = gs_get_chit_number(chit_file)
    amount_per_person = str(chit_info.get("amountPerPerson", "0"))
    gpay = chit_info.get("gpay", "")
    chit_name = chit_info.get("chitName", chit_file.replace(".xlsx", ""))
    contact_phone = str(chit_info.get("contactNumber", "")).strip()

    if contact_phone:
        msg = message.replace("{chitName}", chit_name).replace("{name}", "").replace("{amount}", amount_per_person).replace("{gpay}", gpay)
        result = send_whatsapp_message(contact_phone, msg)
        return jsonify(result)
    else:
        return jsonify({"success": False, "error": "No contact number found"})

@app.route("/send-tomorrow-reminder", methods=["POST"])
@login_required
def send_tomorrow_reminder():
    data = request.get_json()
    message = data.get("message", "")
    chit_date = data.get("date", "")
    chit_number = data.get("chitNumber", "")
    chit_file = data.get("chitFile", "")

    chit_info = gs_get_chit_number(chit_file)
    contact_number = str(chit_info.get("contactNumber", "")).strip()
    chit_name = chit_info.get("chitName", chit_file.replace(".xlsx", ""))

    if contact_number:
        msg = message.replace("{chitName}", chit_name).replace("{name}", "").replace("{date}", chit_date).replace("{chitNumber}", chit_number).replace("{contactNumber}", contact_number)
        result = send_whatsapp_message(contact_number, msg)
        return jsonify(result)
    else:
        return jsonify({"success": False, "error": "No contact number found"})

# ==================== CONFIG ROUTES ====================

@app.route("/get-config")
@admin_required
def get_config():
    token = os.environ.get("WHATSAPP_API_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    masked = {
        "whatsapp_api_token": ("••••" + token[-8:]) if len(token) > 8 else token,
        "whatsapp_phone_number_id": phone_id,
        "configured": bool(token and phone_id)
    }
    return jsonify(masked)

@app.route("/save-config", methods=["POST"])
@admin_required
def save_config_route():
    data = request.get_json()
    if data.get("whatsapp_api_token"):
        os.environ["WHATSAPP_API_TOKEN"] = data["whatsapp_api_token"]
    if data.get("whatsapp_phone_number_id"):
        os.environ["WHATSAPP_PHONE_NUMBER_ID"] = data["whatsapp_phone_number_id"]
    # Persist to .env file so values survive restarts
    try:
        env_vars = {}
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        env_vars[key.strip()] = val.strip()
        if data.get("whatsapp_api_token"):
            env_vars["WHATSAPP_API_TOKEN"] = data["whatsapp_api_token"]
        if data.get("whatsapp_phone_number_id"):
            env_vars["WHATSAPP_PHONE_NUMBER_ID"] = data["whatsapp_phone_number_id"]
        with open(".env", "w") as f:
            for key, val in env_vars.items():
                f.write(f"{key}={val}\n")
    except Exception:
        pass
    return jsonify({"success": True})

@app.route("/send-wa-direct", methods=["POST"])
@admin_required
def send_wa_direct():
    data = request.get_json()
    phone = data.get("phone", "")
    message = data.get("message", "")
    result = send_whatsapp_message(phone, message)
    return jsonify(result)

@app.route("/verify-whatsapp")
@admin_required
def verify_whatsapp():
    """Verify WhatsApp API token and phone number ID are valid."""
    token = os.environ.get("WHATSAPP_API_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        return jsonify({"valid": False, "error": "WhatsApp API not configured."})
    try:
        # Check token by querying the phone number ID
        resp = requests.get(
            f"https://graph.facebook.com/v22.0/{phone_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        result = resp.json()
        if "error" in result:
            err = result["error"]
            code = err.get("code", "")
            msg = err.get("message", "")
            if code == 190:
                return jsonify({"valid": False, "error": "Access token is expired or invalid. Generate a new one from Meta Business Suite."})
            elif code == 200:
                return jsonify({"valid": False, "error": "API permission denied. Your app may be in Development mode — switch to Live in Meta App Dashboard."})
            else:
                return jsonify({"valid": False, "error": f"{msg} (code: {code})"})
        # Success - token and phone ID are valid
        display_name = result.get("verified_name", result.get("display_phone_number", "OK"))
        return jsonify({"valid": True, "phone": result.get("display_phone_number", ""), "name": display_name})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})

# ==================== ADMIN ROUTES ====================

@app.route("/check-role")
@login_required
def check_role():
    return jsonify({"role": session.get("role", "user"), "username": session.get("username", ""), "chitFile": session.get("chitFile", "")})

@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json()
    current_password = data.get("currentPassword", "")
    new_password = data.get("newPassword", "")
    if not current_password or not new_password:
        return jsonify({"success": False, "error": "Please fill in all fields"})
    if len(new_password) < 4:
        return jsonify({"success": False, "error": "New password must be at least 4 characters"})

    username = session.get("username", "")
    # Verify current password
    user = None
    try:
        user = find_user(username)
    except Exception:
        pass

    if user:
        if user.get("password") != current_password:
            return jsonify({"success": False, "error": "Current password is incorrect"})
        # Update in Google Sheets
        try:
            from google_sheets_api import update_user as gs_update_user_fn
            gs_update_user_fn(username, password=new_password)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    else:
        # Fallback to config.json
        cfg = load_config()
        users = cfg.get("users", {})
        if username in users:
            if users[username].get("password") != current_password:
                return jsonify({"success": False, "error": "Current password is incorrect"})
            users[username]["password"] = new_password
            cfg["users"] = users
            save_config(cfg)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "User not found"})

@app.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")

@app.route("/get-users")
@admin_required
def get_users_route():
    users = get_all_users()
    return jsonify([{"username": u["username"], "role": u.get("role", "user"), "email": u.get("email", ""), "chitFile": u.get("chitFile", "")} for u in users])

@app.route("/add-user", methods=["POST"])
@admin_required
def add_user():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user")
    email = data.get("email", "").strip()
    chit_file = data.get("chitFile", "").strip()
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"})
    if not chit_file:
        return jsonify({"success": False, "error": "Assigned Chit is required"})
    success, msg = gs_add_user(username, password, role, email, chit_file)
    return jsonify({"success": success, "error": msg if not success else None})

@app.route("/delete-user", methods=["POST"])
@admin_required
def delete_user():
    data = request.get_json()
    username = data.get("username", "").strip()
    if username == session.get("username"):
        return jsonify({"success": False, "error": "Cannot delete yourself"})
    success, msg = gs_delete_user(username)
    return jsonify({"success": success, "error": msg if not success else None})

@app.route("/update-user", methods=["POST"])
@admin_required
def update_user():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "")
    email = data.get("email", "").strip()
    chit_file = data.get("chitFile", "").strip()
    success, msg = gs_update_user(username, password or None, role, email, chit_file)
    return jsonify({"success": success, "error": msg if not success else None})

# ==================== WHATSAPP BOT (WEBHOOK) ====================

WEBHOOK_VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "chitfund_bot_verify_2026")

# In-memory conversation state per phone number
# { "919876543210": { "step": "select_chit" | "ready", "chitFile": "xxx.xlsx", "chitFiles": [...] } }
_bot_sessions = {}

# Cached mapping: normalized phone → [{"file": "x.xlsx", "chitName": "..."}]
_contact_chit_cache = {"data": {}, "timestamp": 0}
_CONTACT_CACHE_TTL = 120  # seconds

def _normalize_phone(phone):
    """Strip +, leading 0, and country code 91."""
    p = str(phone).strip().replace(" ", "").lstrip("+").lstrip("0")
    if p.startswith("91") and len(p) > 10:
        p = p[2:]
    return p

def _build_contact_chit_map():
    """Build a mapping of phone number → chit files. Uses parallel fetch."""
    from concurrent.futures import ThreadPoolExecutor
    mapping = {}  # normalized_phone → [{"file": ..., "chitName": ...}]

    all_files = []
    try:
        folders = gs_get_chit_folders()
        for folder in folders:
            files = gs_get_chit_files(folder)
            all_files.extend(files)
    except Exception:
        return mapping

    def fetch_info(cf):
        try:
            return cf, gs_get_chit_number(cf)
        except Exception:
            return cf, {}

    # Fetch all chit info in parallel (max 10 threads)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_info, all_files))

    for cf, info in results:
        contact = str(info.get("contactNumber", "")).strip().replace(" ", "")
        clean = _normalize_phone(contact)
        if clean:
            if clean not in mapping:
                mapping[clean] = []
            mapping[clean].append({
                "file": cf,
                "chitName": info.get("chitName", cf.replace(".xlsx", ""))
            })

    return mapping

def _get_chits_for_phone(phone):
    """Get chit files belonging to a phone number, using cache."""
    now = time.time()
    if now - _contact_chit_cache["timestamp"] > _CONTACT_CACHE_TTL or not _contact_chit_cache["data"]:
        _contact_chit_cache["data"] = _build_contact_chit_map()
        _contact_chit_cache["timestamp"] = now

    clean = _normalize_phone(phone)
    return _contact_chit_cache["data"].get(clean, [])

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    """Meta webhook verification."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    print(f"[Webhook] Verify: mode={mode}")
    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        print("[Webhook] ✅ Verified")
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook_receive():
    """Receive incoming WhatsApp messages."""
    body = request.get_json(silent=True)
    if not body:
        return "OK", 200
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "statuses" in value:
                    continue
                for msg in value.get("messages", []):
                    from_number = msg.get("from", "")
                    msg_type = msg.get("type", "")
                    text = ""

                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "").strip()
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        int_type = interactive.get("type", "")
                        if int_type == "list_reply":
                            text = interactive.get("list_reply", {}).get("id", "")
                        elif int_type == "button_reply":
                            text = interactive.get("button_reply", {}).get("id", "")
                    else:
                        continue

                    if from_number and text:
                        print(f"[Bot] 📩 {from_number}: {text} (type={msg_type})")
                        threading.Thread(target=_handle_bot_message, args=(from_number, text), daemon=True).start()
    except Exception as e:
        print(f"[Bot] Error: {e}")
    return "OK", 200

@app.route("/webhook-test")
def webhook_test():
    return jsonify({"status": "ok", "message": "Webhook is reachable!", "verify_token": WEBHOOK_VERIFY_TOKEN})

@app.route("/get-webhook-token")
@admin_required
def get_webhook_token():
    return jsonify({"token": WEBHOOK_VERIFY_TOKEN})

@app.route("/save-webhook-token", methods=["POST"])
@admin_required
def save_webhook_token():
    global WEBHOOK_VERIFY_TOKEN
    data = request.get_json()
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"success": False, "error": "Token cannot be empty"})
    WEBHOOK_VERIFY_TOKEN = token
    os.environ["WEBHOOK_VERIFY_TOKEN"] = token
    try:
        env_vars = {}
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
        env_vars["WEBHOOK_VERIFY_TOKEN"] = token
        with open(".env", "w") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")
    except Exception:
        pass
    return jsonify({"success": True})

# ==================== BOT CONVERSATION LOGIC ====================

def _handle_bot_message(from_number, text):
    """Conversational bot: hi → pick chit → then answer questions."""
    try:
        text_lower = text.lower().strip()
        sess = _bot_sessions.get(from_number, {})

        # ---- RESET: hi / hello / start → show chit list ----
        if text_lower in ("hi", "hello", "hey", "hii", "hai", "start", "reset", "menu"):
            matched = _get_chits_for_phone(from_number)

            if not matched:
                send_whatsapp_message(from_number,
                    "🔍 Sorry, your phone number is not linked to any chit.\n\n"
                    "Please contact the chit administrator to add your number.\n\n"
                    f"📱 Your number: {from_number}"
                )
                return

            if len(matched) == 1:
                m = matched[0]
                _bot_sessions[from_number] = {"step": "ready", "chitFile": m["file"], "chitName": m["chitName"]}
                _send_command_menu(from_number, "👋 Welcome!", f"Your chit: *{m['chitName']}*\n\nSelect an option or type your *name* for payment history.")
                return

            _bot_sessions[from_number] = {"step": "select_chit", "chitFiles": [m["file"] for m in matched], "chitNames": [m["chitName"] for m in matched]}
            _send_chit_selection_list(from_number, matched)
            return

        # ---- Handle interactive chit selection (chit_0, chit_1, etc.) ----
        if text_lower.startswith("chit_"):
            try:
                idx = int(text_lower.replace("chit_", ""))
                sess = _bot_sessions.get(from_number, {})
                chit_files = sess.get("chitFiles", [])
                chit_names = sess.get("chitNames", [])
                if 0 <= idx < len(chit_files):
                    selected = chit_files[idx]
                    chit_name = chit_names[idx] if idx < len(chit_names) else selected.replace(".xlsx", "")
                    _bot_sessions[from_number] = {"step": "ready", "chitFile": selected, "chitName": chit_name}
                    _send_command_menu(from_number, f"✅ {chit_name}", f"You selected *{chit_name}*\n\nSelect an option or type your *name* for payment history.")
                    return
            except (ValueError, IndexError):
                pass

        # ---- Handle interactive command IDs ----
        if text_lower.startswith("cmd_"):
            sess = _bot_sessions.get(from_number, {})
            if sess.get("step") != "ready":
                send_whatsapp_message(from_number, "👋 Send *hi* to get started.")
                return

            cf = sess.get("chitFile", "")
            chit_name = sess.get("chitName", "")

            if text_lower == "cmd_details":
                info = gs_get_chit_number(cf)
                reply = (
                    f"📋 *{info.get('chitName', cf)}* — Full Details\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 Chit Number: *{info.get('chitNumber', '-')}*\n"
                    f"💰 Total Amount: ₹{info.get('totalAmount', '-')}\n"
                    f"📱 GPay: {info.get('gpay', '-')}\n"
                    f"📞 Contact: {info.get('contactNumber', '-')}\n"
                    f"⏳ Balance Chit: {info.get('balanceChit', '-')}"
                )
                send_whatsapp_message(from_number, reply)
                _send_command_menu(from_number, chit_name, "What would you like to do next?")
                return

            if text_lower == "cmd_reminder":
                info = gs_get_chit_number(cf)
                chit_n = info.get("chitName", cf.replace(".xlsx", ""))
                amount = info.get("amountPerPerson", "-")
                gpay = info.get("gpay", "-")
                reply = (
                    f"🔔 Reminder for *{chit_n}*\n\n"
                    f"Hi 👋,\n\n"
                    f"This is a friendly reminder to pay your chit amount of *₹{amount}* for this month.\n\n"
                    f"💳 Gpay/PhonePe to *{gpay}*\n\n"
                    f"Please make the payment at the earliest if not done.\n\n"
                    f"———————————\n\n"
                    f"🔔 *{chit_n}* நினைவூட்டல்\n\n"
                    f"நட்பான நினைவூட்டல்: இந்த மாதத்திற்கான உங்கள் சிட் தொகை *₹{amount}* செலுத்தவும், இன்னும் செலுத்தவில்லை என்றால்.\n\n"
                    f"💳 Gpay/PhonePe க்கு *{gpay}*\n\n"
                    f"Thank you! 🙏"
                )
                send_whatsapp_message(from_number, reply)
                _send_command_menu(from_number, chit_name, "What would you like to do next?")
                return

            if text_lower == "cmd_tomorrow":
                info = gs_get_chit_number(cf)
                chit_n = info.get("chitName", cf.replace(".xlsx", ""))
                chit_num = info.get("chitNumber", "-")
                contact = info.get("contactNumber", "-")
                tomorrow = date.today() + timedelta(days=1)
                tomorrow_str = tomorrow.strftime("%d-%m-%Y")
                reply = (
                    f"🔔 *Reminder: {chit_n} - Chit Tomorrow!*\n\n"
                    f"📅 *Date:* {tomorrow_str}\n"
                    f"📌 *Chit Number:* {chit_num}\n\n"
                    f"Dear Members,\n"
                    f"Tomorrow is the chit day for *{chit_n}*.\n"
                    f"If you want to take the chit, please come and participate.\n\n"
                    f"📞 *Contact:* {contact} (Call to confirm your interest)\n\n"
                    f"———————————\n\n"
                    f"🔔 *நினைவூட்டல்: {chit_n} - நாளை சிட்!*\n\n"
                    f"📅 *தேதி:* {tomorrow_str}\n"
                    f"📌 *சிட் எண்:* {chit_num}\n\n"
                    f"நாளை *{chit_n}* சிட் நடக்கிறது.\n"
                    f"நீங்கள் சிட் எடுக்க விரும்பினால், தயவுசெய்து வருகை தாருங்கள்.\n\n"
                    f"📞 *தொடர்பு எண்:* {contact}\n\n"
                    f"நன்றி! 🙏"
                )
                send_whatsapp_message(from_number, reply)
                _send_command_menu(from_number, chit_name, "What would you like to do next?")
                return

            if text_lower == "cmd_name_search":
                send_whatsapp_message(from_number, "🔍 Please type your *name* as it appears in the chit to get your payment history.")
                return

            if text_lower == "cmd_change":
                _bot_sessions[from_number] = {}
                _handle_bot_message(from_number, "hi")
                return

            return

        # ---- STEP: Waiting for chit selection (typed number fallback) ----
        if sess.get("step") == "select_chit":
            chit_files = sess.get("chitFiles", [])
            chit_names = sess.get("chitNames", [])

            try:
                choice = int(text_lower)
                if 1 <= choice <= len(chit_files):
                    selected = chit_files[choice - 1]
                    chit_name = chit_names[choice - 1] if choice - 1 < len(chit_names) else selected.replace(".xlsx", "")
                    _bot_sessions[from_number] = {"step": "ready", "chitFile": selected, "chitName": chit_name}
                    _send_command_menu(from_number, chit_name, f"You selected *{chit_name}*\n\nSelect an option or type your *name* for payment history.")
                    return
                else:
                    send_whatsapp_message(from_number, f"⚠️ Please send a number between *1* and *{len(chit_files)}*.")
                    return
            except ValueError:
                pass

            for i, cf in enumerate(chit_files):
                name = chit_names[i] if i < len(chit_names) else cf.replace(".xlsx", "")
                if text_lower in name.lower() or text_lower in cf.lower().replace(".xlsx", ""):
                    _bot_sessions[from_number] = {"step": "ready", "chitFile": cf, "chitName": name}
                    _send_command_menu(from_number, name, f"You selected *{name}*\n\nSelect an option or type your *name* for payment history.")
                    return

            send_whatsapp_message(from_number, f"⚠️ I didn't understand. Please select a chit from the list or send a number (1-{len(chit_files)}).")
            return

        # ---- No session yet ----
        if sess.get("step") != "ready":
            send_whatsapp_message(from_number, "👋 Hi! Send *hi* to get started.")
            return

        # ---- STEP: ready — free text (name search or typed commands as fallback) ----
        cf = sess.get("chitFile", "")
        chit_name = sess.get("chitName", "")

        if text_lower in ("change", "switch", "back", "select", "chit"):
            _bot_sessions[from_number] = {}
            _handle_bot_message(from_number, "hi")
            return

        if text_lower in ("help", "?", "commands"):
            _send_command_menu(from_number, chit_name, "Select an option or type your *name* for payment history.")
            return

        if text_lower in ("details", "detail", "info", "full", "all"):
            _handle_bot_message(from_number, "cmd_details")
            return

        if text_lower in ("reminder", "remind", "pay reminder", "payment reminder"):
            _handle_bot_message(from_number, "cmd_reminder")
            return

        if text_lower in ("tomorrow", "chit tomorrow", "tmrw", "tmr"):
            _handle_bot_message(from_number, "cmd_tomorrow")
            return

        # ---- NAME SEARCH ----
        result = _search_member_in_chit(text, cf)
        if result:
            send_whatsapp_message(from_number, result)
            _send_command_menu(from_number, chit_name, "What would you like to do next?")
        else:
            reply = (
                f"🔍 No member found with name *{text}* in *{chit_name}*.\n\n"
                "Please type your name exactly as it appears in the chit."
            )
            send_whatsapp_message(from_number, reply)
            _send_command_menu(from_number, chit_name, "Try again or select an option:")

    except Exception as e:
        print(f"[Bot] Error: {e}")
        try:
            send_whatsapp_message(from_number, "⚠️ Something went wrong. Send *hi* to start again.")
        except Exception:
            pass

def _search_member_in_chit(name, chit_file):
    """Search for a member by name in a specific chit file and return payment info."""
    name_lower = name.lower().strip()
    try:
        view_data = gs_get_chit_view_data(chit_file)
        members_data = view_data.get("members", [])
        if not members_data:
            return None

        for member in members_data:
            if not isinstance(member, dict):
                continue
            member_name = member.get("name", member.get("Name", member.get("NAME", "")))
            if not member_name:
                member_name = str(list(member.values())[0]) if member.values() else ""

            if not member_name or name_lower not in member_name.lower():
                continue

            info = gs_get_chit_number(chit_file)
            result = f"👤 *{member_name}* — {info.get('chitName', chit_file)}\n━━━━━━━━━━━━━━━\n"

            paid_count = 0
            unpaid_count = 0
            unpaid_months = []
            for key, val in member.items():
                key_lower = key.lower()
                if key_lower in ("name", "phone", "number", "sl", "sl.no", "s.no", "sno", "contact"):
                    continue
                status = str(val).strip().lower()
                if status == "paid":
                    paid_count += 1
                elif status and status != "":
                    unpaid_count += 1
                    unpaid_months.append(key)

            result += f"✅ Paid: *{paid_count}* months\n"
            if unpaid_count > 0:
                result += f"❌ Unpaid: *{unpaid_count}* months\n"
                result += f"📅 Pending: {', '.join(unpaid_months[:6])}"
                if len(unpaid_months) > 6:
                    result += f" +{len(unpaid_months)-6} more"
                result += "\n"
            else:
                result += "🎉 All months paid!\n"

            result += f"\n💳 Amount/Month: ₹{info.get('amountPerPerson', '-')}\n"
            result += f"📱 GPay: {info.get('gpay', '-')}"
            return result

    except Exception:
        pass
    return None

if __name__ == "__main__":
    app.run(debug=True, port=5001)
