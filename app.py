from flask import Flask, render_template, session, redirect, url_for, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime, timezone
from better_profanity import profanity
import os
import atexit
import psutil
import socket
import json
import os
import threading
from collections import defaultdict, deque
import time



# ============================================================================
# CONFIGURATION & INITIALIZATION & global datas
# ============================================================================
namespaces = ["/","/chat", "/server-stats", "/hub-stats","/set-username"] ##  list of all namespaces


from init import initialize
features_folder = "features"
if not os.path.exists(features_folder):
    initialize()
socketio = SocketIO(async_mode="threading")
profanity.load_censor_words()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================




def is_blacklisted(text: str) -> bool:
    """Check if text contains profanity"""
    return profanity.contains_profanity(text.lower())


def is_rate_limited(key):
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = rate_limit_data[key]

    # Remove old timestamps
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_COUNT:
        return True

    timestamps.append(now)
    return False


# ============================================================================
# USER TRACKING FEATURE
# ============================================================================

USERS_FILE = os.path.join(features_folder, "users.json")

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
CHAT_FILE = os.path.join(features_folder, "chat", "chat.json")
chat_messages = []
chat_message_id_counter = 1
CHAT_MAX_MESSAGE_LENGTH = 200  # character limit for messages
chat_lock = threading.Lock()
RATE_LIMIT_COUNT = 5          # max messages
RATE_LIMIT_WINDOW = 10        # seconds

rate_limit_data = defaultdict(deque)



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
# STATS FEATURES
# ============================================================================
#global tracking variables for stats
connected_ips = set()  # all unique IPs across all namespaces


# Server stats configuration
STATS_UPDATE_INTERVAL = 3  # seconds
stats_threads = {}
stats_caches = {}
stats_locks = defaultdict(threading.Lock)


def add_ip(ip):
    if ip:
        connected_ips.add(ip)

def remove_ip(ip):
    if ip in connected_ips:
        connected_ips.remove(ip)

def start_stats_broadcaster(namespace, stats_func, interval):
    """Start a background broadcaster for a namespace if not already running."""

    with stats_locks[namespace]:
        if namespace in stats_threads:
            return  # already running

        def broadcaster():
            while True:

                try:
                    stats = stats_func()
                    stats_caches[namespace] = stats
                    socketio.emit("stats_update", stats, namespace=namespace)
                except Exception as e:
                    print(f"{namespace} broadcaster error:", e)

                socketio.sleep(interval)

        stats_threads[namespace] = socketio.start_background_task(broadcaster)


def get_hub_stats():
    return {
        "ips":{
            "total_ips": len(users_data),
            "online_ips": len(connected_ips)
        },
        "usernames": {
            "total_usernames": sum(len(names) for names in users_data.values()),
            "average_usernames_per_ip": round(sum(len(names) for names in users_data.values()) / len(users_data), 2) if users_data else 0
        },
        "server_uptime_seconds": int((datetime.now() - server_start_time).total_seconds()),
        "timestamp": datetime.now().isoformat()
    }


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
    
    # Network
    u1,d1 = int(psutil.net_io_counters().bytes_sent), int(psutil.net_io_counters().bytes_recv)
    time.sleep(0.1)
    u2,d2 = int(psutil.net_io_counters().bytes_sent), int(psutil.net_io_counters().bytes_recv)
    sendSpeed = (u2-u1)*10
    receiveSpeed = (d2-d1)*10
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
            "active_interfaces": active_interfaces,
            "send": sendSpeed,
            "receive": receiveSpeed

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

    # ====================================================================
    # ROUTES - HUB STATS
    # ====================================================================

    @app.route("/hub-stats")
    def hub_stats():
        if "username" not in session or "ip_address" not in session:
            return redirect(url_for("set_username"))
        # Verify username is actually tracked for this IP in users.json
        if not is_valid_username_for_ip(session["ip_address"], session["username"]):
            session.clear()
            return redirect(url_for("set_username"))
        return render_template("hub_stats.html", username=session["username"])

    return app


app = create_app()
atexit.register(exit_function)


# ============================================================================
# SOCKETIO EVENTS - CHAT
# ============================================================================

@socketio.on("connect",namespace="/chat")
def handle_connect():
    if "username" not in session:
        return False
    emit("system_message", f"{session['username']} connected.", broadcast=True,namespace="/chat")


@socketio.on("disconnect",namespace="/chat")
def handle_disconnect():
    if "username" in session:
        emit("system_message", f"{session['username']} left.", broadcast=True,namespace="/chat")


@socketio.on("send_message", namespace="/chat")
def handle_message(data):
    global chat_message_id_counter
    username = session.get("username", "Unknown")
    ip_address = session.get("ip_address", None)
    
    rate_key = f"{ip_address}|{username}"

    if is_rate_limited(rate_key):
        emit(
            "system_message",
            "You're sending messages too quickly. Please slow down.",
            namespace="/chat"
        )
        return

    
    message = data.get("message", "")[:CHAT_MAX_MESSAGE_LENGTH]  # enforce character limit
    is_command = data.get("isCommand", False)
    reply_to_id = data.get("reply_to_id")

    # Basic profanity checks
    if is_blacklisted(username):
        emit("system_message", "Message blocked due to inappropriate content", namespace="/chat")
        return
    if not is_command and is_blacklisted(message):
        emit("system_message", "Message blocked due to inappropriate content", namespace="/chat")
        return

    # Coerce reply_to_id to int if present (defensive)
    if reply_to_id is not None:
        try:
            reply_to_id = int(reply_to_id)
        except (TypeError, ValueError):
            reply_to_id = None

    # Build and append message under lock; also handle popping/saving under the same lock
    popped_msg = None
    with chat_lock:
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
        chat_messages.append(msg)
        chat_message_id_counter += 1

        # enforce in-memory cap and persist popped message safely while still holding the lock
        if len(chat_messages) > CHAT_RECENT_LIMIT:
            popped_msg = chat_messages.pop(0)

    # persist popped message (if any) outside critical path but after we've removed it
    if popped_msg:
        save_chat_message_to_disk(popped_msg)

    # Attach reply metadata (no lock needed here because we only read)
    if reply_to_id:
        original_msg = get_message_by_id(reply_to_id)
        if original_msg:
            msg["reply_to_username"] = original_msg["username"]
            msg["reply_to_message"] = original_msg["message"]

    # Build the response (convert timestamp to isoformat)
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

    emit("chat_message", response, broadcast=True, namespace="/chat")


@socketio.on("message_read",namespace="/chat")
def message_read(data):
    msg_id = data.get("id")
    username = session.get("username")

    for msg in chat_messages:
        if msg['id'] == msg_id:
            # Don't count the message sender as having read their own message
            if username not in msg['read_users'] and username != msg['username']:
                msg['read_users'].add(username)
                msg['read_count'] = len(msg['read_users'])
                emit("update_read_count", {"id": msg_id, "read_count": msg['read_count']}, broadcast=True,namespace="/chat")
            break


@socketio.on("load_older_messages",namespace="/chat")
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
            try:
                disk_msgs = json.load(f)
            except Exception:
                disk_msgs = []
        for msg_data_json in disk_msgs:
            msg_id_int = int(msg_data_json.get("id"))
            if msg_id_int < last_id and msg_id_int not in [m["id"] for m in older_messages]:
                msg_data = {
                    "id": msg_id_int,
                    "username": msg_data_json.get("username"),
                    "message": msg_data_json.get("message"),
                    "timestamp": msg_data_json.get("timestamp"),
                    "read_count": msg_data_json.get("read_count", 0),
                    "ip_address": msg_data_json.get("ip_address")
                }
                if msg_data_json.get("reply_to_id"):
                    msg_data["reply_to_id"] = msg_data_json.get("reply_to_id")
                    msg_data["reply_to_username"] = msg_data_json.get("reply_to_username", "")
                    msg_data["reply_to_message"] = msg_data_json.get("reply_to_message", "")
                older_messages.append(msg_data)

    
    # Sort by ID and send last 50
    older_messages.sort(key=lambda x: x["id"])
    emit("older_messages", older_messages[-50:],namespace="/chat")


@socketio.on("delete_message",namespace="/chat")
def handle_delete_message(data):
    msg_id = data.get("id")
    user_ip = session.get("ip_address")
    
    if not msg_id or not user_ip:
        return
    
    # Find the message
    msg = get_message_by_id(msg_id)
    if not msg:
        emit("system_message", "Message not found",namespace="/chat")
        return
    
    # Check if the user owns this message (same IP)
    if msg.get("ip_address") != user_ip:
        emit("system_message", "You can only delete your own messages",namespace="/chat")
        return
    
    # Mark as deleted
    msg["message"] = "[deleted]"
    msg["deleted"] = True
    
    emit("message_deleted", {"id": msg_id}, broadcast=True,namespace="/chat")


@socketio.on("edit_message",namespace="/chat")
def handle_edit_message(data):
    msg_id = data.get("id")
    new_message = data.get("message", "").strip()[:CHAT_MAX_MESSAGE_LENGTH]
    user_ip = session.get("ip_address")
    
    if not msg_id or not user_ip or not new_message:
        return
    
    # Find the message
    msg = get_message_by_id(msg_id)
    if not msg:
        emit("system_message", "Message not found",namespace="/chat")
        return
    
    # Check if the user owns this message (same IP)
    if msg.get("ip_address") != user_ip:
        emit("system_message", "You can only edit your own messages",namespace="/chat")
        return
    
    # Check for profanity in edited message
    if is_blacklisted(new_message):
        emit("system_message", "Message blocked due to inappropriate content",namespace="/chat")
        return
    
    # Update message
    msg["message"] = new_message
    msg["edited"] = True
    
    emit("message_edited", {"id": msg_id, "message": new_message}, broadcast=True)

# ============================================================================
# SOCKETIO EVENTS - STATS
# ============================================================================


@socketio.on("subscribe_stats", namespace="/server-stats")
def handle_server_subscribe(data=None):
    namespace = "/server-stats"

    # Send immediate snapshot
    stats = get_server_stats()
    emit("stats_update", stats, namespace=namespace)

    # Start broadcaster (only once)
    start_stats_broadcaster(namespace, get_server_stats, STATS_UPDATE_INTERVAL)


@socketio.on("subscribe_stats", namespace="/hub-stats")
def handle_hub_subscribe(data=None):
    namespace = "/hub-stats"


    stats = get_hub_stats()
    emit("stats_update", stats, namespace=namespace)

    start_stats_broadcaster(namespace, get_hub_stats, STATS_UPDATE_INTERVAL)


for ns in namespaces:
    @socketio.on("connect", namespace=ns)
    def handle_connect(ns=ns):  # default arg to capture current namespace
        ip_address = session.get("ip_address")
        add_ip(ip_address)
        print(f"{ip_address} connected to {ns}, total unique IPs: {len(connected_ips)}")

    @socketio.on("disconnect", namespace=ns)
    def handle_disconnect(ns=ns):
        ip_address = session.get("ip_address")
        remove_ip(ip_address)
        print(f"{ip_address} disconnected from {ns}, total unique IPs: {len(connected_ips)}")




# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)