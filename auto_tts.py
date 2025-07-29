import os
import re
import uuid
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
import requests
from pydub import AudioSegment

# ------------------ Konfiguration / Pfade ------------------
BASE_DIR     = Path(__file__).parent
PROMPT_FILE  = BASE_DIR / "prompts" / "base_prompt.md"

DRAFT_DIR    = BASE_DIR / "drafts"
APPROVED_DIR = BASE_DIR / "approved"
PARTS_DIR    = BASE_DIR / "audio_parts"
OUT_DIR      = BASE_DIR / "output"

for p in (DRAFT_DIR, APPROVED_DIR, PARTS_DIR, OUT_DIR):
    p.mkdir(exist_ok=True)

# ------------------ ENV laden ------------------
load_dotenv()  # .env im gleichen Ordner

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ELEVEN_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID   = os.getenv("ELEVEN_VOICE_ID", "IrMGt4vHCJZmo2JER29o")
GPT_MODEL  = os.getenv("GPT_MODEL", "gpt-4o")

# average characters spoken per minute; used for multi-topic mode
CHARS_PER_MIN = 700

if not OPENAI_KEY or not ELEVEN_KEY:
    raise SystemExit("❌ OPENAI_API_KEY oder ELEVEN_API_KEY fehlt in .env")

# ------------------ Helper ------------------
def read_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt-Template fehlt: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")

def generate_script(topic: str, char_target: int) -> str:
    """ Holt das Skript von GPT """
    client = OpenAI(api_key=OPENAI_KEY)
    tmpl = read_prompt_template()
    prompt = tmpl.format(topic=topic, char_target=char_target)

    resp = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    text = resp.choices[0].message.content.strip()
    return text

def save_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8")

def count_chars(text: str) -> int:
    return len(text)

def load_topics(value: str) -> List[str]:
    """Return a list of topics from file or comma-separated string"""
    path = Path(value)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        return [l.strip() for l in lines if l.strip()]
    return [t.strip() for t in value.split(",") if t.strip()]

def calc_target_per_topic(n: int, chars_per_min: int = CHARS_PER_MIN, minutes: int = 60) -> int:
    total = chars_per_min * minutes
    return max(1, total // n)

def split_text_blocks(text: str, max_chars: int = 2500):
    """ Teilt Text an Absatzgrenzen, damit ElevenLabs-Limits nicht reißen """
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    blocks, current = [], ""
    for p in paras:
        if len(current) + len(p) + 2 > max_chars:
            if current:
                blocks.append(current.strip())
            current = p
        else:
            current = (current + "\n\n" + p) if current else p
    if current.strip():
        blocks.append(current.strip())
    return blocks

def tts_chunk(text: str, idx: int, basename: str) -> Path:
    """ Ein Block Text -> MP3 via ElevenLabs """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "speed": 1.0}
    }
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    try:
        r.raise_for_status()
    except Exception:
        print("❌ ElevenLabs Fehlerantwort:")
        print(r.text[:500])
        raise

    fn = PARTS_DIR / f"{basename}_{idx:02d}.mp3"
    with open(fn, "wb") as f:
        f.write(r.content)
    return fn

def merge_parts(files, out_name: str) -> Path:
    """ Schnipsel zusammenfügen -> finale MP3 """
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=350)  # 0,35s Pause
    for f in files:
        combined += AudioSegment.from_file(f) + pause
    out_path = OUT_DIR / f"{out_name}.mp3"
    combined.export(out_path, format="mp3")
    return out_path

# ------------------ CLI ------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Generate & TTS YouTube scripts")
    ap.add_argument("--generate", action="store_true",
                    help="Neuen Draft erzeugen")
    ap.add_argument("--topic", help="Thema für das Skript (bei --generate)")
    ap.add_argument("--topics",
                    help="Datei oder kommagetrennte Liste mehrerer Topics")
    ap.add_argument("--chars", type=int, default=7000,
                    help="Zielzeichenanzahl (10 -+)")
    ap.add_argument("--max_chunk", type=int, default=2500,
                    help="Max Zeichen pro TTS-Chunk")
    ap.add_argument("--approve", metavar="DATEI",
                    help="Draft freigeben & Audio erzeugen")
    ap.add_argument("--basename", default=None,
                    help="Basisname für Audio-Dateien")

    args = ap.parse_args()

    if args.topics:
        topics = load_topics(args.topics)
        if not topics:
            ap.error("Keine Topics gefunden")

        basename = args.basename or f"combined_{uuid.uuid4().hex[:8]}"
        char_target = calc_target_per_topic(len(topics))

        mp3_files = []
        idx = 0
        for topic in topics:
            print(f"📝 Generiere Skript: {topic}")
            text = generate_script(topic, char_target)
            blocks = split_text_blocks(text, max_chars=args.max_chunk)
            for block in blocks:
                idx += 1
                print(f"TTS {idx} …")
                mp3_files.append(tts_chunk(block, idx, basename))

        final_file = merge_parts(mp3_files, basename)
        print("🎧 Fertig:", final_file)
        return

    if args.generate:
        if not args.topic:
            ap.error("--topic ist Pflicht bei --generate")

        text = generate_script(args.topic, args.chars)
        fname = f"{uuid.uuid4().hex[:8]}_{re.sub(r'[^a-z0-9]+', '-', args.topic.lower())}.md"
        draft_path = DRAFT_DIR / fname
        save_text(draft_path, text)

        print(f"📜 Draft gespeichert: {draft_path}")
        print(f"Zeichen: {count_chars(text)} (Ziel {args.chars} ±10%)")
        print("→ Lies/Korrigiere die Datei und rufe danach an:")
        print(f"python auto_tts.py --approve {draft_path.name}")
        return

    if args.approve:
        draft_path = DRAFT_DIR / args.approve
        if not draft_path.exists():
            ap.error(f"Draft nicht gefunden: {draft_path}")

        # In approved kopieren
        text = draft_path.read_text(encoding="utf-8").strip()
        approved_path = APPROVED_DIR / draft_path.name
        save_text(approved_path, text)
        print(f"✅ Approved gespeichert: {approved_path}")

        basename = args.basename or approved_path.stem

        blocks = split_text_blocks(text, max_chars=args.max_chunk)
        print(f"Chunks: {len(blocks)}")

        mp3_files = []
        for i, block in enumerate(blocks):
            print(f"TTS {i+1}/{len(blocks)} …")
            mp3_files.append(tts_chunk(block, i, basename))

        final_file = merge_parts(mp3_files, basename)
        print("🎧 Fertig:", final_file)
        return

    # Wenn nichts angegeben:
    ap.print_help()

if __name__ == "__main__":
    main()
