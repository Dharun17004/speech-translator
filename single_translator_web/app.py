from flask import Flask, render_template, request, jsonify, send_from_directory
from googletrans import Translator, LANGUAGES
from gtts import gTTS
import os
import uuid
import time
import json

# Initialize Flask app
app = Flask(__name__)
# Directory to save temporary audio files (must be inside 'static' for web access)
app.config['UPLOAD_FOLDER'] = 'static/audio'
# IMPORTANT: CHANGE THIS TO A STRONG, UNIQUE KEY IN PRODUCTION!
app.config['SECRET_KEY'] = 'a_new_strong_secret_key_for_flask_sessions'

# Ensure the upload folder exists within the static directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Translator
translator = Translator()

# Helper function for cleaner language name handling
def get_language_name(code):
    """Returns the full language name for a given two-letter code."""
    return LANGUAGES.get(code.lower(), f"Unknown ({code})")

# Function to translate text with retry logic
def translate_text_logic(text, src_lang, dest_lang, max_retries=3, initial_delay=1):
    """
    Translates text with retry mechanism for transient errors.
    Returns translated text and the detected source language code.
    """
    retries = 0
    while retries < max_retries:
        try:
            print(f"Attempting translation (retry {retries + 1}/{max_retries}): '{text}' from {src_lang} to {dest_lang}")
            translated = translator.translate(text, src=src_lang, dest=dest_lang)
            if translated and translated.text:
                return translated.text, translated.src
            else:
                print(f"Translation attempt {retries + 1} returned empty or None for '{text}'.")
                raise Exception("Empty or invalid translation response from Google Translate.")

        except Exception as e:
            retries += 1
            print(f"Translation error (attempt {retries}/{max_retries}): {e}")
            if "too many requests" in str(e).lower() or "timeout" in str(e).lower() or "connection" in str(e).lower() or "bad response from google translate" in str(e).lower():
                delay = initial_delay * (2 ** (retries - 1))
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Non-retryable or unexpected error: {e}. Not retrying.")
                return None, None

    print(f"Failed to translate '{text}' after {max_retries} attempts.")
    return None, None

# Function to synthesize speech and save to a file on the server
def synthesize_speech_to_file(text, lang_code, slow_audio=False):
    """
    Converts text to speech using gTTS, saves it to a temporary file
    in the static/audio directory, and returns the relative URL.
    Includes an option for slow speech.
    """
    try:
        gtts_lang_code = lang_code.split('-')[0]
        print(f"Generating speech for text: '{text[:50]}...' in language: {gtts_lang_code}, Slow: {slow_audio}")
        tts = gTTS(text=text, lang=gtts_lang_code, slow=slow_audio)

        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_filepath = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)

        tts.save(audio_filepath)
        print(f"Audio saved to: {audio_filepath}")
        return f"/static/audio/{audio_filename}"
    except Exception as e:
        print(f"gTTS audio generation error: {e}")
        return None

# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main translation page."""
    sorted_languages = sorted(LANGUAGES.items(), key=lambda item: item[1])
    return render_template('index.html', languages=sorted_languages)


@app.route('/translate', methods=['POST'])
def translate():
    """Handles translation requests from the frontend."""
    data = request.json
    input_text = data.get('text', '').strip()
    src_lang_code = data.get('src_lang', 'en').lower()
    dest_lang_code = data.get('dest_lang', 'ta').lower()
    speak_output = data.get('speak_output', False)
    slow_speech = data.get('slow_speech', False) # New: Get slow speech preference

    src_lang_name = get_language_name(src_lang_code)
    dest_lang_name = get_language_name(dest_lang_code)

    if not input_text:
        return jsonify({
            'original_text': '',
            'translated_text': 'Please enter some text to translate.',
            'audio_url': None,
            'src_lang_name': src_lang_name,
            'dest_lang_name': dest_lang_name,
            'detected_src_lang_code': None
        }), 200

    translated_result_text, detected_src_lang_code = translate_text_logic(input_text, src_lang_code, dest_lang_code)

    audio_url = None
    if translated_result_text and speak_output:
        audio_url = synthesize_speech_to_file(translated_result_text, dest_lang_code, slow_audio=slow_speech)

    final_src_lang_display_name = src_lang_name
    if src_lang_code == 'auto' and detected_src_lang_code:
        final_src_lang_display_name = f"Auto-detected: {get_language_name(detected_src_lang_code)}"

    response_data = {
        'original_text': input_text,
        'translated_text': translated_result_text if translated_result_text is not None else "Translation failed. Please try again or check server logs.",
        'audio_url': audio_url,
        'src_lang_name': final_src_lang_display_name,
        'dest_lang_name': dest_lang_name,
        'detected_src_lang_code': detected_src_lang_code
    }
    return jsonify(response_data)


# --- Main execution ---
if __name__ == '__main__':
    print("Starting Flask web server...")
    print(f"Access the translator at: http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
