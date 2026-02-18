from flask import Flask, render_template, session, redirect, url_for, request
from flask_socketio import SocketIO, emit
from datetime import datetime, timezone
from better_profanity import profanity
import os
import atexit
import psutil
import socket
import json
import os

# ============================================================================
# CONFIGURATION & INITIALIZATION
# ============================================================================

socketio = SocketIO(async_mode="threading")
profanity.load_censor_words()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_blacklisted(text: str) -> bool:
    """Check if text contains profanity"""
    return profanity.contains_profanity(text.lower())


# ============================================================================
# USER TRACKING FEATURE
# ============================================================================

USERS_FILE = "features/users.json"

def load_users():
    """Load users data from disk"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users_data):
    """Save users data to disk"""
    os.makedirs("features", exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, indent=2, ensure_ascii=False)

def track_username(ip_address, username):
    """Track a new username for an IP address"""
    users_data = load_users()
    if ip_address not in users_data:
        users_data[ip_address] = []
    
    # Only add if not already in the list
    if username not in users_data[ip_address]:
        users_data[ip_address].append(username)
    
    save_users(users_data)

def get_usernames_for_ip(ip_address):
    """Get all usernames created by an IP address"""
    users_data = load_users()
    return users_data.get(ip_address, [])

def get_most_recent_username(ip_address):
    """Get the most recent (last) username for an IP address"""
    usernames = get_usernames_for_ip(ip_address)
    return usernames[-1] if usernames else None

def is_valid_username_for_ip(ip_address, username):
    """Verify that a username is actually registered for an IP address in users.json"""
    usernames = get_usernames_for_ip(ip_address)
    return username in usernames

def username_exists(username):
    """Check if a username exists anywhere in users.json (across all IPs)"""
    users_data = load_users()
    for ip, usernames in users_data.items():
        if username in usernames:
            return True
    return False

users_data = load_users()


# ============================================================================
# CHAT FEATURE
# ============================================================================

# Chat data
CHAT_RECENT_LIMIT = 100
CHAT_FILE = "features/chat/chat.json"
chat_messages = []
chat_message_id_counter = 1
CHAT_MAX_MESSAGE_LENGTH = 200  # character limit for messages


def load_chat_messages():
    """Load chat messages from disk into memory"""
    global chat_message_id_counter
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            messages_data = json.load(f)
            for msg_data in messages_data:
                msg_obj = {
                    "id": msg_data["id"],
                    "username": msg_data["username"],
                    "message": msg_data["message"],
                    "timestamp": datetime.fromisoformat(msg_data["timestamp"]),
                    "read_count": msg_data.get("read_count", 0),
                    "read_users": set(),
                    "reply_to_id": msg_data.get("reply_to_id"),
                    "ip_address": msg_data.get("ip_address"),
                    "edited": msg_data.get("edited", False)
                }
                chat_messages.append(msg_obj)
                chat_message_id_counter = max(chat_message_id_counter, msg_data["id"] + 1)
        chat_messages[:] = chat_messages[-CHAT_RECENT_LIMIT:]  # only keep recent in RAM


def get_message_by_id(msg_id):
    """Get a message from memory by ID"""
    for msg in chat_messages:
        if msg["id"] == msg_id:
            return msg
    return None


def save_chat_message_to_disk(msg):
    """Save a single chat message to disk (appended to JSON array)"""
    os.makedirs("features/chat", exist_ok=True)
    # Load existing messages
    existing_messages = []
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            existing_messages = json.load(f)
    # Append new message
    msg_data = {
        "id": msg["id"],
        "username": msg["username"],
        "message": msg["message"],
        "timestamp": msg["timestamp"].isoformat(),
        "read_count": msg.get("read_count", 0),
        "reply_to_id": msg.get("reply_to_id"),
        "ip_address": msg.get("ip_address"),
        "edited": msg.get("edited", False)
    }
    existing_messages.append(msg_data)
    # Write back
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_messages, f, indent=2, ensure_ascii=False)


def save_all_chat_messages_to_disk():
    """Save all in-memory chat messages to disk"""
    if chat_messages:
        os.makedirs("features/chat", exist_ok=True)
        messages_data = []
        for msg in chat_messages:
            msg_data = {
                "id": msg["id"],
                "username": msg["username"],
                "message": msg["message"],
                "timestamp": msg["timestamp"].isoformat(),
                "read_count": msg.get("read_count", 0),
                "reply_to_id": msg.get("reply_to_id"),
                "ip_address": msg.get("ip_address"),
                "edited": msg.get("edited", False)
            }
            messages_data.append(msg_data)
        with open(CHAT_FILE, "w", encoding="utf-8") as f:
            json.dump(messages_data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(chat_messages)} chat messages to disk on shutdown.")


# Load chat messages on startup
load_chat_messages()
server_start_time = datetime.now()  # Record when server starts (after loading old messages)


# ============================================================================
# SERVER STATS FEATURE
# ============================================================================

# Server stats configuration
STATS_UPDATE_INTERVAL = 3  # seconds

def get_server_stats():
    """Gather current server statistics"""
    # RAM Usage
    ram = psutil.virtual_memory()
    ram_percent = ram.percent
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)
    
    # CPU Usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count()
    
    # Disk Usage
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    disk_used_gb = disk.used / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)
    
    # Network - get connection count
    try:
        net_connections = len(psutil.net_connections())
    except:
        net_connections = 0
    
    # Network interfaces info
    net_if = psutil.net_if_stats()
    active_interfaces = sum(1 for iface in net_if.values() if iface.isup)
    
    return {
        "ram": {
            "percent": round(ram_percent, 1),
            "used_gb": round(ram_used_gb, 2),
            "total_gb": round(ram_total_gb, 2)
        },
        "cpu": {
            "percent": round(cpu_percent, 1),
            "count": cpu_count
        },
        "disk": {
            "percent": round(disk_percent, 1),
            "used_gb": round(disk_used_gb, 2),
            "total_gb": round(disk_total_gb, 2)
        },
        "network": {
            "connections": net_connections,
            "active_interfaces": active_interfaces
        },
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# APP INITIALIZATION
# ============================================================================


def exit_function():
    """Save all data when server stops"""
    save_all_chat_messages_to_disk()


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
    app.config.update(
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )


    socketio.init_app(app)

    def get_network_display():
        """Return a friendly network name (FQDN if available, otherwise local IP)."""
        try:
            fqdn = socket.getfqdn()
            if fqdn and '.' in fqdn and fqdn != socket.gethostname():
                return fqdn
            # Fallback to local IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            finally:
                s.close()
            return local_ip
        except Exception:
            return 'LAN'

    @app.context_processor
    def inject_network_name():
        return {"network_name": get_network_display()}

    # ====================================================================
    # ROUTES - CORE
    # ====================================================================

    @app.route("/")
    def home():
        if "username" not in session or "ip_address" not in session:
            return redirect(url_for("set_username"))
        # Verify username is actually tracked for this IP in users.json
        if not is_valid_username_for_ip(session["ip_address"], session["username"]):
            session.clear()
            return redirect(url_for("set_username"))
        return render_template("home.html", username=session["username"])

    @app.route("/set-username", methods=["GET", "POST"])
    def set_username():
        ip_address = request.remote_addr
        session["ip_address"] = ip_address
        change_mode = request.args.get("change") is not None
        
        # Check if this IP already has a username (only auto-load if not explicitly changing and not already in session)
        existing_username = get_most_recent_username(ip_address)
        if existing_username and "username" not in session and not change_mode:
            # Auto-load the most recent username
            session["username"] = existing_username
            return redirect(url_for("home"))
        
        error_message = None
        if request.method == "POST":
            username = request.form["username"].strip()
            user_previous_usernames = get_usernames_for_ip(ip_address)
            if not username:
                error_message = "Username cannot be empty"
            elif is_blacklisted(username):
                error_message = "Username contains inappropriate content"
            elif username_exists(username) and username not in user_previous_usernames:
                # Only block if username exists AND it's not one of their own previous usernames
                error_message = f"Username '{username}' is already taken"
            else:
                session["username"] = username
                session["ip_address"] = ip_address
                track_username(ip_address, username)
                # Reload users data in memory
                global users_data
                users_data = load_users()
                return redirect(url_for("home"))
        
        # Display existing usernames for context if they exist, excluding current username
        existing_usernames = get_usernames_for_ip(ip_address)
        current_username = session.get("username")
        # Filter out the current username from the list
        existing_usernames = [u for u in existing_usernames if u != current_username]
        return render_template("set_username.html", existing_usernames=existing_usernames, change_mode=change_mode, error_message=error_message)

    # ====================================================================
    # ROUTES - CHAT
    # ====================================================================

    @app.route("/chat")
    def chat():
        if "username" not in session or "ip_address" not in session:
            return redirect(url_for("set_username"))
        # Verify username is actually tracked for this IP in users.json
        if not is_valid_username_for_ip(session["ip_address"], session["username"]):
            session.clear()
            return redirect(url_for("set_username"))
        return render_template("chat.html", username=session["username"], ip_address=session.get("ip_address"))

    @app.route("/get-user-ip")
    def get_user_ip():
        """Return the current user's IP address"""
        if "ip_address" not in session:
            session["ip_address"] = request.remote_addr
        return {"ip_address": session.get("ip_address")}

    # ====================================================================
    # ROUTES - SERVER STATS
    # ====================================================================

    @app.route("/server-stats")
    def server_stats():
        if "username" not in session or "ip_address" not in session:
            return redirect(url_for("set_username"))
        # Verify username is actually tracked for this IP in users.json
        if not is_valid_username_for_ip(session["ip_address"], session["username"]):
            session.clear()
            return redirect(url_for("set_username"))
        return render_template("server_stats.html", username=session["username"])

    return app


app = create_app()
atexit.register(exit_function)


# ============================================================================
# SOCKETIO EVENTS - CHAT
# ============================================================================

@socketio.on("connect")
def handle_connect():
    if "username" not in session:
        return False
    emit("system_message", f"{session['username']} connected.", broadcast=True)


@socketio.on("disconnect")
def handle_disconnect():
    if "username" in session:
        emit("system_message", f"{session['username']} left.", broadcast=True)


@socketio.on("send_message")
def handle_message(data):
    global chat_message_id_counter
    username = session.get("username", "Unknown")
    ip_address = session.get("ip_address", None)
    message = data.get("message", "")[:CHAT_MAX_MESSAGE_LENGTH]  # enforce character limit
    is_command = data.get("isCommand", False)  # Check if this is a command
    reply_to_id = data.get("reply_to_id")  # Get the ID of the message this is replying to

    # Check username is never blacklisted, but skip content check for commands
    if is_blacklisted(username):
        emit("system_message", "Message blocked due to inappropriate content")
        return
    
    # Only check message content for profanity if it's not a command
    if not is_command and is_blacklisted(message):
        emit("system_message", "Message blocked due to inappropriate content")
        return

    msg = {
        "id": chat_message_id_counter,
        "username": username,
        "message": message,
        "timestamp": datetime.now(),
        "read_count": 0,
        "read_users": set(),
        "reply_to_id": reply_to_id,
        "ip_address": ip_address
    }
    
    # If this is a reply, add the replied-to message info
    if reply_to_id:
        original_msg = get_message_by_id(reply_to_id)
        if original_msg:
            msg["reply_to_username"] = original_msg["username"]
            msg["reply_to_message"] = original_msg["message"]
    
    chat_messages.append(msg)
    if len(chat_messages) > CHAT_RECENT_LIMIT:
        save_chat_message_to_disk(chat_messages.pop(0))

    chat_message_id_counter += 1

    # Build the response with reply info
    response = {
        "id": msg["id"],
        "username": msg["username"],
        "message": msg["message"],
        "timestamp": msg["timestamp"].isoformat(),
        "read_count": msg["read_count"],
        "reply_to_id": msg.get("reply_to_id"),
        "ip_address": msg.get("ip_address")
    }
    
    if "reply_to_username" in msg:
        response["reply_to_username"] = msg["reply_to_username"]
        response["reply_to_message"] = msg["reply_to_message"]
    
    emit("chat_message", response, broadcast=True)


@socketio.on("message_read")
def message_read(data):
    msg_id = data.get("id")
    username = session.get("username")

    for msg in chat_messages:
        if msg['id'] == msg_id:
            # Don't count the message sender as having read their own message
            if username not in msg['read_users'] and username != msg['username']:
                msg['read_users'].add(username)
                msg['read_count'] = len(msg['read_users'])
                emit("update_read_count", {"id": msg_id, "read_count": msg['read_count']}, broadcast=True)
            break


@socketio.on("load_older_messages")
def load_older_messages(data):
    last_id = data.get("last_id")
    user_ip = session.get("ip_address")
    
    # Handle None or invalid last_id - load all messages
    if last_id is None or last_id == float('inf'):
        last_id = float('inf')
    
    older_messages = []
    
    # First, include messages from memory that are older than last_id
    for msg in chat_messages:
        if msg["id"] < last_id:
            msg_data = {
                "id": msg["id"],
                "username": msg["username"],
                "message": msg["message"],
                "timestamp": msg["timestamp"].isoformat(),
                "read_count": msg["read_count"],
                "ip_address": msg.get("ip_address")
            }
            if msg.get("reply_to_id"):
                msg_data["reply_to_id"] = msg["reply_to_id"]
                msg_data["reply_to_username"] = msg.get("reply_to_username", "")
                msg_data["reply_to_message"] = msg.get("reply_to_message", "")
            older_messages.append(msg_data)
    
    # Then, load from disk for messages older than what's in memory
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split('|', 5)
                if len(parts) >= 4:
                    msg_id, username, timestamp, *rest = parts
                    msg_id_int = int(msg_id)
                    
                    # Handle multiple formats
                    if msg_id_int < last_id and msg_id_int not in [m["id"] for m in older_messages]:
                        if len(rest) == 3:  # New format with reply_to_id and ip: id|username|timestamp|reply_to_id|ip|message
                            reply_to_id_str, ip_addr, message = rest
                            reply_to_id = int(reply_to_id_str) if reply_to_id_str else None
                        elif len(rest) == 2:  # Format with reply_to_id, no ip: id|username|timestamp|reply_to_id|message
                            reply_to_id_str, message = rest
                            reply_to_id = int(reply_to_id_str) if reply_to_id_str else None
                            ip_addr = None
                        else:  # Old format without reply_to_id: id|username|timestamp|message
                            message = rest[0]
                            reply_to_id = None
                            ip_addr = None
                        
                        msg_data = {
                            "id": msg_id_int,
                            "username": username,
                            "message": message,
                            "timestamp": timestamp,
                            "read_count": 0,
                            "ip_address": ip_addr
                        }
                        if reply_to_id:
                            msg_data["reply_to_id"] = reply_to_id
                            msg_data["reply_to_username"] = ""
                            msg_data["reply_to_message"] = ""
                        older_messages.append(msg_data)
    
    # Sort by ID and send last 50
    older_messages.sort(key=lambda x: x["id"])
    emit("older_messages", older_messages[-50:])


# ============================================================================
# SOCKETIO EVENTS - SERVER STATS
# ============================================================================

@socketio.on("request_stats")
def handle_stats_request(data):
    """Send current server stats when requested"""
    stats = get_server_stats()
    emit("server_stats", stats)


@socketio.on("subscribe_stats")
def handle_subscribe_stats(data):
    """Subscribe to real-time server stats updates"""
    # Send initial stats
    stats = get_server_stats()
    emit("server_stats", stats)
    
    # To implement continuous updates, emit stats on an interval
    # The client will use a timer for regular requests instead


@socketio.on("delete_message")
def handle_delete_message(data):
    msg_id = data.get("id")
    user_ip = session.get("ip_address")
    
    if not msg_id or not user_ip:
        return
    
    # Find the message
    msg = get_message_by_id(msg_id)
    if not msg:
        emit("system_message", "Message not found")
        return
    
    # Check if the user owns this message (same IP)
    if msg.get("ip_address") != user_ip:
        emit("system_message", "You can only delete your own messages")
        return
    
    # Mark as deleted
    msg["message"] = "[deleted]"
    msg["deleted"] = True
    
    emit("message_deleted", {"id": msg_id}, broadcast=True)


@socketio.on("edit_message")
def handle_edit_message(data):
    msg_id = data.get("id")
    new_message = data.get("message", "").strip()[:CHAT_MAX_MESSAGE_LENGTH]
    user_ip = session.get("ip_address")
    
    if not msg_id or not user_ip or not new_message:
        return
    
    # Find the message
    msg = get_message_by_id(msg_id)
    if not msg:
        emit("system_message", "Message not found")
        return
    
    # Check if the user owns this message (same IP)
    if msg.get("ip_address") != user_ip:
        emit("system_message", "You can only edit your own messages")
        return
    
    # Check for profanity in edited message
    if is_blacklisted(new_message):
        emit("system_message", "Message blocked due to inappropriate content")
        return
    
    # Update message
    msg["message"] = new_message
    msg["edited"] = True
    
    emit("message_edited", {"id": msg_id, "message": new_message}, broadcast=True)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)