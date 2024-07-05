import logging
from typing import List

from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import ebooklib
from ebooklib import epub
from langdetect import detect
import os
from audiobook_generator.language_detection import (load_language_options, get_supported_languages,
                                                    get_supported_locales)
import dotenv

dotenv.load_dotenv()

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load language options from CSV
LANGUAGE_OPTIONS = load_language_options('../audiobook_generator/language_detection/text-to-speech-languages.csv')
SUPPORTED_LANGUAGES = get_supported_languages(LANGUAGE_OPTIONS)
SUPPORTED_LOCALES = get_supported_locales(LANGUAGE_OPTIONS)

# User configurations
user_configs = {}


# Define command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    instructions = (
        "Welcome to the eBook to Audio converter bot!\n\n"
        "To use this bot, simply send me an .epub file, and I'll convert it to multiple .mp3 audio files.\n\n"
        "You can set your preferred voice gender using the /config command.\n\n"
        "Commands:\n"
        "/start - Show these instructions\n"
        "/config - Set your default voice gender (male/female)\n"
        "/languages - Show supported languages"
    )
    await update.message.reply_text(instructions)


async def config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_config = user_configs.get(user_id, {'voice_gender': 'female'})  # Default to female if not set

    keyboard = [
        [InlineKeyboardButton("Edit", callback_data="edit_config")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_config")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Current default voice gender: {current_config['voice_gender']}",
        reply_markup=reply_markup
    )


async def show_languages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    languages = "\n".join(SUPPORTED_LANGUAGES)
    await update.message.reply_text(f"Supported languages:\n\n{languages}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "edit_config":
        keyboard = [
            [InlineKeyboardButton("Male", callback_data="set_voice_male")],
            [InlineKeyboardButton("Female", callback_data="set_voice_female")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Choose your default voice gender:", reply_markup=reply_markup)

    elif query.data == "cancel_config":
        await query.edit_message_text("Configuration cancelled.")

    elif query.data.startswith("set_voice_"):
        user_id = update.effective_user.id
        voice_gender = query.data.split("_")[-1]
        user_configs[user_id] = {'voice_gender': voice_gender}
        await query.edit_message_text(f"Config default voice gender changed to {voice_gender}")

    elif ":" in query.data:  # This is for language option selection
        locale, file_name = query.data.split(':', 1)
        await query.edit_message_text(text=f"Selected option: {locale}")
        logger.info(f"process_ebook(update, context, {file_name}, {locale})")
        await process_ebook(update, context, file_name, locale)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Get the file
    file = await context.bot.get_file(update.message.document.file_id)

    # Download the file
    file_name = update.message.document.file_name
    await file.download_to_drive(file_name)

    # Detect language
    detected_language = detect_language(file_name)

    if detected_language == "unknown":
        await update.message.reply_text("Sorry, I couldn't detect the language of this ebook. Please try another one.")
        os.remove(file_name)
        return

    split_detected_language = detected_language.split("-")
    if split_detected_language[0] == 'zh':
        detected_language = 'zh'
    else:
        detected_language = split_detected_language[0] + '-' + split_detected_language[1].upper()
    # Check if the language is supported
    matching_locales = [locale for locale in SUPPORTED_LOCALES if locale.startswith(detected_language)]

    if matching_locales:
        await ask_language_option(update, context, file_name, matching_locales)
    else:
        await update.message.reply_text(f"Sorry, the detected language '{detected_language}' is not supported.")
        os.remove(file_name)


def detect_language(file_name: str) -> str:
    # Read the ebook
    book = epub.read_epub(file_name)

    # Extract text from content
    all_text = ""
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        content_text = soup.get_text()
        all_text += content_text
        if len(all_text) > 1000:  # Get a sample of about 1000 characters
            break

    # Clean the text
    all_text = ' '.join(all_text.split())  # Remove extra whitespace

    # Detect language
    try:
        return detect(all_text)
    except:
        return "unknown"


async def ask_language_option(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name: str,
                              matching_locales: List[str]) -> None:
    keyboard = [
        [InlineKeyboardButton(locale, callback_data=f"{locale}:{file_name}")]
        for locale in matching_locales
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose the language option:", reply_markup=reply_markup)


async def process_ebook(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name: str, locale: str) -> None:
    user_id = update.effective_user.id
    voice_gender = user_configs.get(user_id, {}).get('voice_gender', 'female')

    main_lang = locale.split('-')[0]
    voices = LANGUAGE_OPTIONS[main_lang][locale][voice_gender]

    if voices:
        voice = voices[0]  # Choose the first available voice
        logger.info(f"Processing {voice_gender} for {main_lang} with {voice}")
        await update.message.reply_text(f"Processing your ebook with {voice} voice. This may take a while...")

        # Here you would call your existing text-to-audio conversion function
        # For demonstration, we'll just simulate the process
        # TODO: call package's conversion service and send back
        # # Simulating audio file creation
        # audio_files = [f"audio_{i}.mp3" for i in range(3)]  # Assume 3 audio files are created
        #
        # # Send audio files
        # for audio_file in audio_files:
        #     # In reality, you would create these files in your text-to-audio conversion process
        #     with open(audio_file, 'w') as f:  # Simulating file creation
        #         f.write("Audio content")
        #
        #     with open(audio_file, 'rb') as audio:
        #         await context.bot.send_audio(chat_id=update.effective_chat.id, audio=audio)
        #
        #     # Clean up
        #     os.remove(audio_file)
        #
        # # Clean up the ebook file
        # os.remove(file_name)

        await update.message.reply_text("Audio conversion complete!")
    else:
        await update.message.reply_text(f"Sorry, no {voice_gender} voice available for the selected language.")


def main() -> None:
    # Create the Application and pass it your bot's token
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT")).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("config", config))
    application.add_handler(CommandHandler("languages", show_languages))
    application.add_handler(MessageHandler(filters.Document.FileExtension("epub"), handle_document))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == '__main__':
    main()
