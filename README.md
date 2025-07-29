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

### Process multiple topics

```bash
python auto_tts.py --topics topics.txt [--basename NAME]
```

`topics.txt` must contain one topic per line. You can also provide a
comma-separated list directly. For each topic the script generates a segment so
that the total length is roughly one hour of narration. All generated audio
parts are merged into a single mp3 under `output/`.

Run `python auto_tts.py -h` to see all available options.


## GUI Usage

A basic Tkinter interface is available in `auto_tts_gui.py`. Run the script
and enter one or more topics when prompted. For each topic a draft is
presented for approval, followed by the generated audio. Once all segments are
approved a final mp3 is created combining all pieces.

```bash
python auto_tts_gui.py
```
