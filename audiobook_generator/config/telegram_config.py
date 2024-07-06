import argparse

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.tts_providers.base_tts_provider import get_supported_tts_providers


class CustomGeneralConfig(GeneralConfig):
    def __init__(self, custom_args: dict):
        # Create a new argparse.Namespace object
        args = argparse.Namespace()

        # Define default values for all attributes based on the argparse configuration
        default_values = {
            # General arguments
            'input_file': None,  # Required argument, no default
            'output_folder': None,  # Required argument, no default
            'tts': get_supported_tts_providers()[0],  # Assumes this function exists and returns a list
            'log': "INFO",
            'preview': False,
            'no_prompt': False,
            'language': "en-US",
            'newline_mode': "double",
            'title_mode': "auto",
            'chapter_start': 4, # TODO: for debugging purposes
            'chapter_end': 6,# TODO: for debugging purposes
            'output_text': False,
            'remove_endnotes': False,
            'voice_name': None,
            'output_format': None,
            'model_name': None,

            # Edge TTS specific arguments
            'voice_rate': None,
            'voice_volume': None,
            'voice_pitch': None,
            'proxy': None,

            # Azure/Edge TTS specific arguments
            'break_duration': "1250",
        }

        # Set default values for all attributes
        for attr, value in default_values.items():
            setattr(args, attr, value)

        # Override with custom arguments
        for key, value in custom_args.items():
            if key in default_values:
                setattr(args, key, value)
            else:
                print(f"Warning: '{key}' is not a recognized attribute and will be ignored.")

        # Call the parent constructor
        super().__init__(args)

    def __str__(self):
        return super.__str__(self)


if __name__ == "__main__":
    # Usage example
    custom_args = {
        'input_file': 'my_book.epub',
        'output_folder': 'output',
        'language': 'en-US',
        'voice_name': 'en-US-JennyNeural'
    }

    custom_general_config = CustomGeneralConfig(custom_args)
