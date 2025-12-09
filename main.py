import os
import json
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DISCOURSE_URL = os.environ.get("DISCOURSE_URL")
DISCOURSE_API_KEY = os.environ.get("DISCOURSE_API_KEY")
DISCOURSE_USER = "ExternalPointsBot"  # Your bot's exact username
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- SETUP AI ---
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- DATABASE (Simple JSON) ---
# NOTE: On free hosting (Render), this file will reset if the server restarts.
# For permanent points, you would need an external database (like Mongo or Google Sheets).
DB_FILE = "user_points.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

app = Flask(__name__)

@app.route('/', methods=['GET'])
def wake_up():
    return "Bot is awake and tracking points!", 200

@app.route('/webhook', methods=['POST'])
def discourse_webhook():
    data = request.json
    
    # 1. Check if the post is valid (not a system message, not the bot itself)
    if 'post' not in data: 
        return "Not a post", 200
        
    post = data['post']
    username = post['username']
    raw_text = post['raw'].strip()
    topic_id = post['topic_id']
    post_number = post['post_number']

    # Ignore our own posts
    if username == DISCOURSE_USER:
        return jsonify({"status": "ignored"}), 200

    # 2. TRIGGER CHECK: Does it start with / or mention the bot?
    is_command = raw_text.startswith("/")
    is_mention = f"@{DISCOURSE_USER}" in raw_text
    
    if not (is_command or is_mention):
        return jsonify({"status": "ignored", "reason": "no_trigger"}), 200

    # 3. POINTS LOGIC (Python handles this, not AI)
    db = load_db()
    if username not in db:
        db[username] = {"points": 0, "last_daily": "", "last_weekly": "", "last_monthly": ""}
    
    reply_message = ""
    current_time = datetime.now()
    
    # helper to check time difference
    def check_cooldown(last_time_str, hours_needed):
        if not last_time_str: return True
        last_time = datetime.fromisoformat(last_time_str)
        return (current_time - last_time) > timedelta(hours=hours_needed)

    # --- COMMANDS ---
    
    # DAILY (+3)
    if "daily" in raw_text.lower():
        if check_cooldown(db[username]["last_daily"], 24):
            db[username]["points"] += 3
            db[username]["last_daily"] = current_time.isoformat()
            save_db(db)
            reply_message = f"✅ @{username} claimed daily! **+3 Points**. Total: {db[username]['points']}"
        else:
            reply_message = f"⏳ @{username}, you can only use /daily once every 24 hours."

    # WEEKLY (+9)
    elif "weekly" in raw_text.lower():
        if check_cooldown(db[username]["last_weekly"], 168): # 168 hours in a week
            db[username]["points"] += 9
            db[username]["last_weekly"] = current_time.isoformat()
            save_db(db)
            reply_message = f"✅ @{username} claimed weekly! **+9 Points**. Total: {db[username]['points']}"
        else:
            reply_message = f"⏳ @{username}, you can only use /weekly once every 7 days."

    # MONTHLY (+15)
    elif "monthly" in raw_text.lower():
        if check_cooldown(db[username]["last_monthly"], 720): # approx 30 days
            db[username]["points"] += 15
            db[username]["last_monthly"] = current_time.isoformat()
            save_db(db)
            reply_message = f"✅ @{username} claimed monthly! **+15 Points**. Total: {db[username]['points']}"
        else:
            reply_message = f"⏳ @{username}, you can only use /monthly once a month."

    # CHECK POINTS
    elif "points" in raw_text.lower():
        reply_message = f"📊 @{username} currently has **{db[username]['points']} points**."

    # 4. AI FALLBACK (If it was a ping but NOT a points command)
    else:
        # Pass to Gemini for a normal chat reply
        try:
            prompt = f"You are {DISCOURSE_USER}. The user said: {raw_text}. Reply helpfully and briefly."
            ai_response = model.generate_content(prompt)
            reply_message = ai_response.text
        except Exception as e:
            reply_message = "I'm having trouble thinking right now."

    # 5. SEND REPLY
    if reply_message:
        post_url = f"{DISCOURSE_URL}/posts.json"
        payload = {
            "topic_id": topic_id,
            "raw": reply_message,
            "reply_to_post_number": post_number
        }
        headers = {
            "Api-Key": DISCOURSE_API_KEY,
            "Api-Username": DISCOURSE_USER,
            "Content-Type": "application/json"
        }
        requests.post(post_url, json=payload, headers=headers)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
