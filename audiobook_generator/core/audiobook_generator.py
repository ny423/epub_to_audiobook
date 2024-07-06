import logging
from fileinput import FileInput
from typing import Callable, Awaitable, Union
import os

from telegram import Audio

from audiobook_generator.book_parsers.base_book_parser import get_book_parser
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider

logger = logging.getLogger(__name__)


def confirm_conversion():
    print("Do you want to continue? (y/n)")
    answer = input()
    if answer.lower() != "y":
        print("Aborted.")
        exit(0)


def get_total_chars(chapters):
    total_characters = 0
    for title, text in chapters:
        total_characters += len(text)
    return total_characters


class AudiobookGenerator:
    def __init__(self, config: GeneralConfig, command_line_mode: bool = True,
                 send_message: Callable[[str], Awaitable[None]] = None,
                 send_audio: Callable[[str], Awaitable[None]] = None):
        self.config = config
        logger.setLevel(config.log)
        self.command_line_mode = command_line_mode
        self.send_message = send_message
        self.send_audio = send_audio

    async def run(self):
        try:
            book_parser = get_book_parser(self.config)
            tts_provider = get_tts_provider(self.config)

            os.makedirs(self.config.output_folder, exist_ok=True)
            chapters = book_parser.get_chapters(tts_provider.get_break_string())
            chapters = [(title, text) for title, text in chapters if text.strip()]

            # Check chapter start and end args
            if self.config.chapter_start < 1 or self.config.chapter_start > len(chapters):
                raise ValueError(
                    f"Chapter start index {self.config.chapter_start} is out of range. Check your input."
                )
            if self.config.chapter_end < -1 or self.config.chapter_end > len(chapters):
                raise ValueError(
                    f"Chapter end index {self.config.chapter_end} is out of range. Check your input."
                )
            if self.config.chapter_end == -1:
                self.config.chapter_end = len(chapters)
            if self.config.chapter_start > self.config.chapter_end:
                raise ValueError(
                    f"Chapter start index {self.config.chapter_start} is larger than chapter end index {self.config.chapter_end}. Check your input."
                )

            chapters = chapters[self.config.chapter_start - 1:self.config.chapter_end]
            await self.send_message(f"Chapters count: {len(chapters)}.")
            await self.send_message(
                f"Converting chapters from {self.config.chapter_start} to {self.config.chapter_end}.")

            total_characters = get_total_chars(chapters)
            await self.send_message(f"✨ Total characters in selected book: {total_characters} ✨")
            rough_price = tts_provider.estimate_cost(total_characters)
            await self.send_message(f"Estimate book voiceover would cost you roughly: ${rough_price:.2f}")

            for idx, (title, text) in enumerate(chapters, start=1):
                if idx < self.config.chapter_start:
                    logger.info(f"skipping Chapter {idx}")
                    continue
                if idx > self.config.chapter_end:
                    logger.info(f"quitting at Chapter {idx}")
                    break

                if self.config.preview:
                    await self.send_message(
                        f"Previewing convert chapter {idx}/{len(chapters)}: {title}, characters: {len(text)}")
                else:
                    await self.send_message(f"Converting chapter {idx}/{len(chapters)}: {title}, characters: {len(text)}")

                if self.config.output_text:
                    text_file = os.path.join(self.config.output_folder, f"{idx:04d}_{title}.txt")
                    with open(text_file, "w", encoding='utf-8') as file:
                        file.write(text)

                if self.config.preview:
                    continue

                output_file = os.path.join(self.config.output_folder,
                                           f"{idx:04d}_{title}.{tts_provider.get_output_file_extension()}")

                audio_tags = AudioTags(title, book_parser.get_book_author(), book_parser.get_book_title(), idx)
                tts_provider.text_to_speech(text, output_file, audio_tags)

                if self.send_audio:
                    logger.info(f"Sending audio to {output_file}")
                    await self.send_audio(output_file)
                    logger.info(f"Removing audio from {output_file}")
                    os.remove(output_file)  # Remove the file after sending

                await self.send_message(f"✅ Converted and sent chapter {idx}/{len(chapters)}: {title}")

            await self.send_message(f"All chapters converted and sent. 🎉🎉🎉")

        except KeyboardInterrupt:
            await self.send_message("Job stopped by user.")
            raise
        except Exception as e:
            await self.send_message(f"An error occurred: {str(e)}")
            raise

    async def send_message(self, message: str):
        if self.send_message:
            await self.send_message(message)
        else:
            logger.info(message)
