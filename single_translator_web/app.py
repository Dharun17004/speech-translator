from flask import Flask, render_template, request, jsonify, send_from_directory
from googletrans import Translator, LANGUAGES
from gtts import gTTS
import os
import tempfile
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
    """
    retries = 0
    while retries < max_retries:
        try:
            print(f"Attempting translation (retry {retries + 1}/{max_retries}): '{text}' from {src_lang} to {dest_lang}")
            translated = translator.translate(text, src=src_lang, dest=dest_lang)
            if translated and translated.text:
                return translated.text
            else:
                # If translate returns None or empty text, it's still a failure
                print(f"Translation attempt {retries + 1} returned empty or None for '{text}'.")
                # This could be due to a specific error from googletrans that doesn't raise an exception
                raise Exception("Empty or invalid translation response from Google Translate.")

        except Exception as e:
            retries += 1
            print(f"Translation error (attempt {retries}/{max_retries}): {e}")
            # Check for common network/rate limit related errors in the exception string
            if "too many requests" in str(e).lower() or "timeout" in str(e).lower() or "connection" in str(e).lower() or "bad response from google translate" in str(e).lower():
                delay = initial_delay * (2 ** (retries - 1)) # Exponential backoff
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                # For other unexpected errors, log and fail immediately
                print(f"Non-retryable or unexpected error: {e}. Not retrying.")
                return None # Return None on persistent failure

    print(f"Failed to translate '{text}' after {max_retries} attempts.")
    return None

# Function to synthesize speech and save to a file on the server
def synthesize_speech_to_file(text, lang_code):
    """
    Converts text to speech using gTTS, saves it to a temporary file
    in the static/audio directory, and returns the relative URL.
    """
    try:
        # gTTS language code usually expects a two-letter code (e.g., 'en', 'es')
        gtts_lang_code = lang_code.split('-')[0]
        print(f"Generating speech for text: '{text[:50]}...' in language: {gtts_lang_code}") # Log first 50 chars
        tts = gTTS(text=text, lang=gtts_lang_code)

        # Generate a unique filename to avoid conflicts
        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_filepath = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)

        tts.save(audio_filepath)
        print(f"Audio saved to: {audio_filepath}")
        return f"/static/audio/{audio_filename}" # Return the URL to access the audio
    except Exception as e:
        print(f"gTTS audio generation error: {e}")
        return None

# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main translation page."""
    # Pass languages to the template for dropdowns, sorted alphabetically by name
    sorted_languages = sorted(LANGUAGES.items(), key=lambda item: item[1])
    return render_template('index.html', languages=sorted_languages)

@app.route('/translate', methods=['POST'])
def translate():
    """Handles the translation request from the web page."""
    data = request.json # Get JSON data sent from the frontend

    input_text = data.get('text', '').strip() # Get and strip whitespace from text
    src_lang_code = data.get('src_lang', 'en').lower()
    dest_lang_code = data.get('dest_lang', 'es').lower()
    speak_output = data.get('speak_output', False)

    # Get full language names for display
    src_lang_name = get_language_name(src_lang_code)
    dest_lang_name = get_language_name(dest_lang_code)

    if not input_text:
        return jsonify({
            'original_text': '',
            'translated_text': 'Please enter some text to translate.',
            'audio_url': None,
            'src_lang_name': src_lang_name,
            'dest_lang_name': dest_lang_name
        }), 200 # Still return 200 OK for user-friendly message

    # Perform translation
    translated_text = translate_text_logic(input_text, src_lang_code, dest_lang_code)

    audio_url = None
    if translated_text and speak_output:
        # Generate speech if requested. Use dest_lang_code for TTS.
        audio_url = synthesize_speech_to_file(translated_text, dest_lang_code)

    # Prepare response data, handling cases where translation failed
    response_data = {
        'original_text': input_text,
        'translated_text': translated_text if translated_text is not None else "Translation failed. Please try again or check server logs.",
        'audio_url': audio_url,
        'src_lang_name': src_lang_name,
        'dest_lang_name': dest_lang_name
    }
    return jsonify(response_data)

# --- Main execution ---
if __name__ == '__main__':
    print("Starting Flask web server...")
    print(f"Access the translator at: http://127.0.0.1:5000")
    # Set debug=True for development (auto-reloads, better error messages)
    # Set debug=False for production and use a production WSGI server like Gunicorn
    app.run(debug=True, host='0.0.0.0', port=5000)
