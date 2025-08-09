import os
import re
import asyncio
import logging
from collections import deque
import threading
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from flask import Flask, request

# Flask app setup
app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

link_queue = deque()
sending_interval = 1
queue_lock = asyncio.Lock()

# Function to extract Terabox links using an updated regex
def extract_terabox_links(text):
    terabox_pattern = r"(https?://\S*(terabox\.com|1024terabox\.com|terafileshare\.com)/\S+)"
    return re.findall(terabox_pattern, text)

# Handler for incoming messages (now handles all messages, not just channel posts)
async def handle_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post or update.message
    
    if message and (message.caption or message.text):
        message_text = message.caption or message.text
        links = extract_terabox_links(message_text)

        if links:
            for link in links:
                link_queue.append(link)
            logging.info(f"Added {len(links)} links to the queue.")
            # A good practice is to provide some feedback to the user
            await message.reply_text(f"Links found and added to queue: {len(links)}")
        else:
            logging.info("No Terabox links found in the message.")

# Command to set the sending interval
async def set_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_interval = int(context.args[0])
        if new_interval <= 0:
            await update.message.reply_text("Interval must be a positive number.")
            return

        global sending_interval
        sending_interval = new_interval
        await update.message.reply_text(
            f"Sending interval updated to {sending_interval} minutes."
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Please provide a valid number in minutes. Example: `/set_interval 10`"
        )

# Function to process the queue and send links
async def send_links_periodically(application: Application):
    while True:
        await asyncio.sleep(sending_interval * 60)
        async with queue_lock:
            if link_queue:
                link_to_send = link_queue.popleft()
                command_text = f"/dl {link_to_send}"
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID, text=command_text
                )
                logging.info(f"Sent link: {command_text}")
            else:
                logging.info("Queue is empty, waiting for new links.")

# Basic health check endpoint for the web server
@app.route("/")
def home():
    return "Bot is running!", 200

# Function to run the bot's polling loop
def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        MessageHandler(filters.PHOTO | filters.TEXT | filters.Document.ALL, handle_posts)
    )
    application.add_handler(
        CommandHandler("set_interval", set_interval_command)
    )
    
    # Start the periodic sending task
    asyncio.create_task(send_links_periodically(application))
    
    application.run_polling()

def main():
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
