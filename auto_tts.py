import os
import re
import uuid
import shutil
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
IMAGES_DIR   = BASE_DIR / "images"
PROJECTS_DIR = BASE_DIR / "projects"

for p in (DRAFT_DIR, APPROVED_DIR, PARTS_DIR, OUT_DIR, IMAGES_DIR, PROJECTS_DIR):
    p.mkdir(exist_ok=True)

# ------------------ ENV laden ------------------
load_dotenv()  # .env im gleichen Ordner

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ELEVEN_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID   = os.getenv("ELEVEN_VOICE_ID", "IrMGt4vHCJZmo2JER29o")
GPT_MODEL  = os.getenv("GPT_MODEL", "gpt-4o")

# average characters spoken per minute; used for multi-topic mode
CHARS_PER_MIN = 700
USER_AGENT = os.getenv("USER_AGENT", "yt_auto_tts/1.0 (+https://example.com)")

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

def slugify(value: str) -> str:
    """Return a filesystem-friendly version of *value*"""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

def load_topics(value: str) -> List[str]:
    """Return a list of topics from file or comma-separated string"""
    path = Path(value)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip()]
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

def search_wikimedia_images(query, limit: int = 3) -> List[dict]:
    """Search Wikimedia Commons for freely licensed images.

    ``query`` may be a single string or a list of strings. The API will be
    queried sequentially until at least ``limit`` unique images are collected
    or all queries are exhausted. A list of dictionaries with ``title``, ``url``
    and ``license`` is returned.
    """
    if isinstance(query, str):
        queries = [query]
    else:
        queries = list(query)

    api = "https://commons.wikimedia.org/w/api.php"
    headers = {"User-Agent": USER_AGENT}

    results: List[dict] = []
    seen = set()

    for q in queries:
        if len(results) >= limit:
            break
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": q,
            "gsrlimit": limit - len(results),
            "gsrnamespace": 6,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
        }

        try:
            r = requests.get(api, params=params, headers=headers, timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Wikimedia request failed for '{q}': {e}")
            continue
        data = r.json()

        for page in data.get("query", {}).get("pages", {}).values():
            info = page.get("imageinfo", [{}])[0]
            url = info.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            license = (
                info.get("extmetadata", {})
                .get("LicenseShortName", {})
                .get("value")
            )
            results.append({
                "title": page.get("title"),
                "url": url,
                "license": license,
            })
            if len(results) >= limit:
                break

    return results


def search_unsplash_images(query, limit: int = 3) -> List[dict]:
    """Search Unsplash for images if an access key is provided.

    The environment variable ``UNSPLASH_ACCESS_KEY`` must be set. A list of
    dictionaries with ``title``, ``url`` and ``license`` is returned. If no
    key is available or a request fails, an empty list is returned.
    """
    access_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not access_key:
        return []

    if isinstance(query, str):
        queries = [query]
    else:
        queries = list(query)

    headers = {"User-Agent": USER_AGENT, "Authorization": f"Client-ID {access_key}"}
    api = "https://api.unsplash.com/search/photos"

    results: List[dict] = []
    seen = set()

    for q in queries:
        if len(results) >= limit:
            break
        params = {"query": q, "per_page": limit - len(results)}
        try:
            r = requests.get(api, params=params, headers=headers, timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Unsplash request failed for '{q}': {e}")
            continue
        data = r.json()
        for item in data.get("results", []):
            url = item.get("urls", {}).get("regular")
            if not url or url in seen:
                continue
            seen.add(url)
            results.append({
                "title": item.get("description") or item.get("alt_description"),
                "url": url,
                "license": "Unsplash License",
            })
            if len(results) >= limit:
                break

    return results


def extract_image_queries(text: str) -> List[str]:
    """Return one search query per paragraph of ``text``."""
    queries = []
    for para in re.split(r"\n\s*\n", text):
        words = re.findall(r"[A-Za-z0-9']+", para)
        if words:
            queries.append(" ".join(words[:5]))
    return queries


def search_images_for_script(text: str, per_query: int = 1) -> List[dict]:
    """Gather images for each paragraph of ``text``.

    For every paragraph in the script one search query is created. Results
    from Wikimedia Commons are combined with images from Unsplash if an access
    key is configured. The total number of returned images is roughly
    ``per_query`` times the number of paragraphs.
    """
    queries = extract_image_queries(text)
    images: List[dict] = []
    for q in queries:
        images.extend(search_wikimedia_images(q, limit=per_query))
        if len(images) < per_query * len(queries):
            images.extend(search_unsplash_images(q, limit=per_query))
    return images[: per_query * len(queries)]

def tts_chunk(text: str, idx: int, basename: str) -> Path:
    """ Ein Block Text -> MP3 via ElevenLabs """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "speed": 1.0}
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=180)
        r.raise_for_status()
    except requests.RequestException as e:
        print("❌ ElevenLabs Fehlerantwort:")
        if 'r' in locals():
            print(r.text[:500])
        print(e)
        raise

    fn = PARTS_DIR / f"{basename}_{idx:02d}.mp3"
    with open(fn, "wb") as f:
        f.write(r.content)
    return fn

def merge_parts(files, out_name: str, dest_dir: Path | None = None) -> Path:
    """ Schnipsel zusammenfügen -> finale MP3 """
    if dest_dir is None:
        dest_dir = OUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=350)  # 0,35s Pause
    for f in files:
        combined += AudioSegment.from_file(f) + pause
    out_path = dest_dir / f"{out_name}.mp3"
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

        project_dir = PROJECTS_DIR / slugify(basename)
        project_dir.mkdir(parents=True, exist_ok=True)

        mp3_files = []
        idx = 0
        for topic in topics:
            print(f"📝 Generiere Skript: {topic}")
            text = generate_script(topic, char_target)
            save_text(project_dir / f"{slugify(topic)}.md", text)

            images_src = IMAGES_DIR / slugify(topic)
            if images_src.exists():
                dest = project_dir / "images" / slugify(topic)
                shutil.copytree(images_src, dest, dirs_exist_ok=True)

            blocks = split_text_blocks(text, max_chars=args.max_chunk)
            for block in blocks:
                idx += 1
                print(f"TTS {idx} …")
                mp3_files.append(tts_chunk(block, idx, basename))

        final_file = merge_parts(mp3_files, slugify(basename), dest_dir=project_dir)
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
        topic_slug = basename.split("_", 1)[1] if "_" in basename else basename

        project_dir = PROJECTS_DIR / slugify(topic_slug)
        project_dir.mkdir(parents=True, exist_ok=True)

        save_text(project_dir / f"{topic_slug}.md", text)

        images_src = IMAGES_DIR / slugify(topic_slug)
        if images_src.exists():
            dest = project_dir / "images"
            shutil.copytree(images_src, dest, dirs_exist_ok=True)

        blocks = split_text_blocks(text, max_chars=args.max_chunk)
        print(f"Chunks: {len(blocks)}")

        mp3_files = []
        for i, block in enumerate(blocks):
            print(f"TTS {i+1}/{len(blocks)} …")
            mp3_files.append(tts_chunk(block, i, topic_slug))

        final_file = merge_parts(mp3_files, topic_slug, dest_dir=project_dir)
        print("🎧 Fertig:", final_file)
        return

    # Wenn nichts angegeben:
    ap.print_help()

if __name__ == "__main__":
    main()
