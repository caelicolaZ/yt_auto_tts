# yt_auto_tts

This project automates generating short YouTube scripts with ChatGPT and
converts them to spoken audio via the ElevenLabs API.

## Setup

1. Create a Python virtual environment and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Provide API keys in a `.env` file located in the project root:

```dotenv
OPENAI_API_KEY=your-openai-key
ELEVEN_API_KEY=your-elevenlabs-key
# Optional settings
ELEVEN_VOICE_ID=your-voice-id   # defaults to IrMGt4vHCJZmo2JER29o
GPT_MODEL=gpt-4o                # model used for generation
```

The script reads these variables using `python-dotenv` when it starts.

## CLI Usage

The main entry point is `auto_tts.py`.

### Generate a draft

```bash
python auto_tts.py --generate --topic "The Sea Bishop" --chars 7000
```

A markdown draft is created in the `drafts/` folder. Review and edit the
file before approving it.

### Approve and create audio

```bash
python auto_tts.py --approve <draft_file> [--basename NAME] [--max_chunk 2500]
```

This copies the file to `approved/`, splits the text into chunks and calls
the ElevenLabs API to generate individual audio files. Finally all parts are
merged into a single mp3 placed in the `output/` directory.

Run `python auto_tts.py -h` to see all available options.

