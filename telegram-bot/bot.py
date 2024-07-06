import logging
import uuid
from typing import List, Union

from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Audio
from telegram._utils.types import FileInput
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, \
    CallbackQueryHandler, ConversationHandler
import ebooklib
from ebooklib import epub
from langdetect import detect
import os

from audiobook_generator.config.telegram_config import CustomGeneralConfig
from audiobook_generator.language_detection import (load_language_options, get_supported_languages,
                                                    get_supported_locales)
from audiobook_generator.core.audiobook_generator import AudiobookGenerator
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

# Define the new download path
DOWNLOAD_PATH = "./input_books"

# Ensure the download directory exists
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Define states
SELECTING_LANGUAGE, SELECTING_MODE, ENTERING_START_CHAPTER, ENTERING_END_CHAPTER = range(4)


def get_send_message(update: Update, context: CallbackQueryHandler):
    if update.message:
        send_func = update.message.reply_text
    elif update.callback_query.message:
        send_func = update.callback_query.message.reply_text
    else:
        logger.error("Unable to determine message source")
        return
    return send_func


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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Current operation cancelled. Send me an EPUB file when you're ready to start again."
    )
    return ConversationHandler.END


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


def detect_language(file_path: str) -> str:
    # Read the ebook
    book = epub.read_epub(file_path)

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
    except Exception:
        return "unknown"


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("handle_document: Received a document")
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        file_name = update.message.document.file_name
        file_path = os.path.join('./input_books', file_name)
        logger.info(f"Downloading file to: {file_path}")
        await file.download_to_drive(file_path)
        logger.info(f"File downloaded successfully: {file_path}")

        # Here you would normally detect the language and get matching locales
        # For this example, we'll use dummy data
        # matching_locales = ['en-US', 'en-GB', 'es-ES']
        detected_language = detect_language(file_path)
        if detected_language == 'zh-cn':
            matching_locales = ['zh-CN']
        elif detected_language == 'zh-tw':
            matching_locales = ['zh-HK', 'zh-TW']
        else:
            matching_locales = [locale for locale in SUPPORTED_LOCALES if locale.startswith(detected_language)]
        logger.info(f"Matching locales: {matching_locales}")

        logger.info("Calling ask_language_option")
        return await ask_language_option(update, context, file_path, matching_locales)
    except Exception as e:
        logger.exception(f"An error occurred in handle_document: {str(e)}")
        await update.message.reply_text("An error occurred while processing your document. Please try again.")
        return ConversationHandler.END


async def ask_language_option(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str,
                              matching_locales: list) -> int:
    logger.info(f"ask_language_option: called for file {file_path}")

    try:
        file_id = str(uuid.uuid4())

        if 'file_paths' not in context.user_data:
            context.user_data['file_paths'] = {}
        context.user_data['file_paths'][file_id] = {
            'path': file_path,
            'preview': False,
            'start_chapter': 1,
            'end_chapter': -1
        }

        logger.info(f"Created file_id: {file_id}")
        logger.info(f"Matching locales: {matching_locales}")

        keyboard = [
            [InlineKeyboardButton(locale, callback_data=f"lang:{locale}:{file_id}")]
            for locale in matching_locales
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        logger.info("Preparing to send message with language options")

        if update.message:
            logger.info("Sending reply to message")
            sent_message = await update.message.reply_text("Please choose the language option:",
                                                           reply_markup=reply_markup)
            logger.info(f"Message sent: {sent_message.message_id}")
        elif update.callback_query:
            logger.info("Editing message with callback query")
            edited_message = await update.callback_query.edit_message_text("Please choose the language option:",
                                                                           reply_markup=reply_markup)
            logger.info(f"Message edited: {edited_message.message_id}")
        else:
            logger.error("ask_language_option: Neither message nor callback_query found in update")
            return ConversationHandler.END

        logger.info("ask_language_option: Successfully sent/edited message with language options")
        return SELECTING_LANGUAGE

    except Exception as e:
        logger.exception(f"An error occurred in ask_language_option: {str(e)}")
        return ConversationHandler.END


# Update language_selected function
async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    logger.info(f"language_selected: called with data: {query.data}")

    _, locale, file_id = query.data.split(':')
    context.user_data['file_paths'][file_id]['locale'] = locale

    keyboard = [
        [InlineKeyboardButton("Preview", callback_data=f"mode:preview:{file_id}")],
        [InlineKeyboardButton("Process", callback_data=f"mode:process:{file_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Language selected: {locale}\nChoose mode:", reply_markup=reply_markup)
    return SELECTING_MODE


async def mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    _, mode, file_id = query.data.split(':')
    file_config = context.user_data['file_paths'][file_id]

    if mode == 'preview':
        file_config['preview'] = True
        await query.edit_message_text("Starting preview mode...")
        await process_ebook(update, context, file_config['path'], file_config['locale'], preview=True)
        return ConversationHandler.END
    else:
        await query.edit_message_text("Enter the starting chapter number (start from chapter 1):")
        return ENTERING_START_CHAPTER


async def enter_start_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        start_chapter = int(update.message.text)
        if start_chapter < 1:
            raise ValueError("Invalid start chapter number")
        file_id = list(context.user_data['file_paths'].keys())[-1]  # Get the last added file_id
        context.user_data['file_paths'][file_id]['start_chapter'] = start_chapter
        await update.message.reply_text(
            f"Starting chapter set to {start_chapter}. Now enter the ending chapter number (default: -1 for all):")
        return ENTERING_END_CHAPTER
    except ValueError:
        await update.message.reply_text("Please enter a valid number for the starting chapter. (start from chapter 1)")
        return ENTERING_START_CHAPTER


async def enter_end_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        end_chapter = int(update.message.text)
        file_id = list(context.user_data['file_paths'].keys())[-1]  # Get the last added file_id
        file_config = context.user_data['file_paths'][file_id]

        # if end_chapter < 1 or end_chapter <= context.user_data['start_chapter']:
        logger.info(context.user_data)
        if end_chapter < 1 or end_chapter <= context.user_data['file_paths'][file_id]['start_chapter']:
            raise ValueError("Invalid end chapter number")
        file_config['end_chapter'] = end_chapter

        await update.message.reply_text(f"Ending chapter set to {end_chapter}. Starting to process the ebook...")
        await process_ebook(update, context, file_config['path'], file_config['locale'],
                            preview=False,
                            start_chapter=file_config['start_chapter'],
                            end_chapter=file_config['end_chapter'])
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number for the ending chapter. (default: -1 for all)")
        return ENTERING_END_CHAPTER


async def process_ebook(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, locale: str, preview: bool,
                        start_chapter: int = 1, end_chapter: int = -1) -> None:
    user_id = update.effective_user.id
    voice_gender = user_configs.get(user_id, {}).get('voice_gender', 'female')

    main_lang = locale.split('-')[0]
    voices = LANGUAGE_OPTIONS[main_lang][locale][voice_gender]

    send_func = get_send_message(update, context)

    if voices:
        voice = voices[0]  # Choose the first available voice
        logger.info(f"Processing {voice_gender} for {main_lang} with {voice}")

        await send_func(f"Processing your ebook with {voice} voice. This may take a while...")

        custom_args = {
            'input_file': file_path,
            'output_folder': './output-audios',
            'language': locale,
            'voice_name': voice,
            'tts': 'azure',  # or whatever TTS provider you're using
            'preview': preview,
            'no_prompt': True,
            'chapter_start': start_chapter,
            'chapter_end': end_chapter
        }

        custom_general_config = CustomGeneralConfig(custom_args)

        async def send_audio(audio_file_path: str):
            try:
                with open(audio_file_path, 'rb') as audio:
                    await context.bot.send_audio(chat_id=update.effective_chat.id, audio=audio)
                logger.info(f"Audio file sent successfully: {audio_file_path}")
            except Exception as e:
                logger.exception(f"Error sending audio file {audio_file_path}: {str(e)}")

        generator = AudiobookGenerator(custom_general_config, False, send_func, send_audio)

        try:
            await generator.run()

            if not preview:
                # Send audio files
                audio_files = sorted([f for f in os.listdir('./output-audios') if f.endswith('.mp3')])
                for audio_file in audio_files:
                    file_path = os.path.join('./output-audios', audio_file)
                    with open(file_path, 'rb') as audio:
                        await context.bot.send_audio(chat_id=update.effective_chat.id, audio=audio)
                    os.remove(file_path)

                await send_func("All audio files have been sent and deleted from the server.")
            else:
                await send_func("Preview completed. No audio files were generated.")
        except Exception as e:
            await send_func(f"An error occurred during processing: {str(e)}")
        finally:
            # Clean up
            for file in os.listdir('./output-audios'):
                os.remove(os.path.join('./output-audios', file))
            os.remove(file_path)  # Remove the original ebook file

    else:
        await send_func(f"Sorry, no {voice_gender} voice available for the selected language.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("An unhandled exception occurred:", exc_info=context.error)


def main() -> None:
    # Create the Application and pass it your bot's token
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT")).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.FileExtension("epub"), handle_document)],
        states={
            SELECTING_LANGUAGE: [CallbackQueryHandler(language_selected, pattern=r"^lang:")],
            SELECTING_MODE: [CallbackQueryHandler(mode_selected, pattern=r"^mode:")],
            ENTERING_START_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_chapter)],
            ENTERING_END_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_chapter)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))

    application.add_error_handler(error_handler)

    logger.info("Bot is ready to start polling")
    application.run_polling()


if __name__ == '__main__':
    main()
