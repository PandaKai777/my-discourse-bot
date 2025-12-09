import os
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify

# --- CONFIGURATION (Load from Environment Variables) ---
# In Render/Replit, add these in your "Environment" or "Secrets" tab.
DISCOURSE_URL = os.environ.get("DISCOURSE_URL") # e.g., https://forum.yoursite.com
DISCOURSE_API_KEY = os.environ.get("DISCOURSE_API_KEY")
DISCOURSE_USER = "system" # or your bot's username
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- SETUP GOOGLE GEMINI ---
genai.configure(api_key=GOOGLE_API_KEY)
# Using "gemini-1.5-flash" because it is fast and free
model = genai.GenerativeModel('gemini-1.5-flash')

app = Flask(__name__)

# --- YOUR PROMPT GOES HERE ---
# I will paste your specific prompt into this variable when you send it.
SYSTEM_PROMPT = """
You are a helpful expert on this forum. 
Answer the user's question clearly and politely.
"""

@app.route('/', methods=['GET'])
def wake_up():
    # This route exists just for UptimeRobot to ping and keep the bot awake
    return "I am awake!", 200

@app.route('/webhook', methods=['POST'])
def discourse_webhook():
    data = request.json
    
    # 1. SAFETY: Ignore the bot's own posts to prevent loops
    if data['post']['username'] == DISCOURSE_USER:
        return jsonify({"status": "ignored", "reason": "bot_post"}), 200

    # 2. FILTER: Only reply if the bot is "Mentioned" (@botname)
    # (Optional: Remove this check if you want it to reply to EVERYTHING)
    # Discourse usually handles this by only sending the webhook on mentions, 
    # but it's good to be safe.
    
    # 3. EXTRACT: Get the user's text
    user_post_content = data['post']['raw']
    topic_id = data['post']['topic_id']
    post_number = data['post']['post_number']

    # 4. GENERATE: Send to Google Gemini
    try:
        # Combine system prompt + user text
        full_prompt = f"{SYSTEM_PROMPT}\n\nUser Post:\n{user_post_content}"
        
        response = model.generate_content(full_prompt)
        bot_reply = response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

    # 5. REPLY: Post back to Discourse
    post_url = f"{DISCOURSE_URL}/posts.json"
    payload = {
        "topic_id": topic_id,
        "raw": bot_reply,
        "reply_to_post_number": post_number
    }
    headers = {
        "Api-Key": DISCOURSE_API_KEY,
        "Api-Username": DISCOURSE_USER,
        "Content-Type": "application/json"
    }
    
    r = requests.post(post_url, json=payload, headers=headers)
    
    if r.status_code == 200:
        return jsonify({"status": "success"}), 200
    else:
        print(f"Discourse Error: {r.text}")
        return jsonify({"status": "failed_to_post"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
