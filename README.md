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

## Searching for images

The helper function `search_wikimedia_images()` can fetch freely licensed
images from Wikimedia Commons for a given topic.

```python
from auto_tts import search_wikimedia_images

images = search_wikimedia_images("Sea Bishop", limit=2)
for img in images:
    print(img["url"])
```

Use this to collect illustrative material for each script segment.


## GUI Usage

A basic Tkinter interface is available in `auto_tts_gui.py`. Run the script
and enter one or more topics when prompted. For each topic a draft is
presented for approval. After approving the text you can review a few freely
licensed images from Wikimedia Commons in a small dialog and decide which ones
to save. Selected images are downloaded under `images/<topic>/`. Next, the
audio for that topic is generated and must be approved. Once all segments are
approved a final mp3 is created combining all pieces.

```bash
python auto_tts_gui.py
```

To test just the image search and approval workflow without running the
full pipeline, use the `--test-images` option. Provide a topic with
`--topic` (defaults to "Sperm Whale vs Colossal Squid"):

```bash
python auto_tts_gui.py --test-images --topic "Sea Bishop"
```

### Wikimedia User-Agent

Wikimedia requires a descriptive `User-Agent` header for API and file requests.
Set the environment variable `USER_AGENT` to something that identifies your
application, for example:

```bash
export USER_AGENT="yt_auto_tts/1.0 (contact: you@example.com)"
```

The helper functions automatically include this header when querying and
downloading images.
