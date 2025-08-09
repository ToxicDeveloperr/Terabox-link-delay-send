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
# Replace with your actual bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Replace with your group chat ID
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
# Define the port from environment variables, defaulting to 8080
PORT = int(os.environ.get("PORT", 8080))

# Basic configuration for logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Queue to store links for sequential processing
link_queue = deque()
# Default sending interval in minutes
sending_interval = 1
# A lock to ensure only one task processes the queue at a time
queue_lock = asyncio.Lock()


# Function to extract Terabox links using regex
def extract_terabox_links(text):
    terabox_pattern = r"(https?://\S*terabox\.com/\S+)"
    return re.findall(terabox_pattern, text)


# Handler for incoming messages
async def handle_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post and (update.channel_post.caption or update.channel_post.text):
        message_text = update.channel_post.caption or update.channel_post.text
        links = extract_terabox_links(message_text)

        if links:
            for link in links:
                link_queue.append(link)
            logging.info(f"Added {len(links)} links to the queue.")


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
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run the Flask web server in the main thread
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
