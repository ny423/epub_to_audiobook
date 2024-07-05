from typing import Dict, List

import pandas as pd


def load_language_options(file_path: str = 'text-to-speech-languages.csv') -> Dict[
    str, Dict[str, Dict[str, List[str]]]]:
    df = pd.read_csv(file_path)
    language_options = {}

    for _, row in df.iterrows():
        locale = row['Locale (BCP-47)']
        voices = row['Text to speech voices'].split(") ")
        lang_name = row['Language']
        # print(voices)

        # Extract main language code (e.g., 'en' from 'en-US')
        main_lang = locale.split('-')[0]

        # Initialize main language if not present
        if main_lang not in language_options:
            language_options[main_lang] = {}

        # Initialize sub-language
        language_options[main_lang][locale] = {"lang_name": lang_name, "male": [], "female": []}

        # Process voices
        for voice in voices:
            voice_name = voice.split()[0]
            if '(Female' in voice:
                language_options[main_lang][locale]["female"].append(voice_name)
            elif '(Male' in voice:
                language_options[main_lang][locale]["male"].append(voice_name)

    return language_options


def get_voice_by_gender(options: Dict[str, List[str]], gender: str) -> str:
    voices = options.get(gender.lower(), [])
    return voices[0] if voices else None


def get_supported_languages(options: Dict[str, Dict[str, Dict[str, List[str]]]]) -> List[str]:
    return list(options.keys())


def get_supported_locales(options: Dict[str, Dict[str, Dict[str, List[str]]]]) -> List[str]:
    return [locale for lang in options.values() for locale in lang.keys()]


if __name__ == '__main__':
    language_options = load_language_options()
    print(language_options)
    print(get_supported_languages(language_options))
    print(get_supported_locales(language_options))
