import os
import re
import uuid
import subprocess
import shutil
import tkinter as tk
from io import BytesIO
from tkinter import simpledialog, messagebox, scrolledtext

import requests
from PIL import Image, ImageTk

from auto_tts import (
    generate_script,
    split_text_blocks,
    tts_chunk,
    merge_parts,
    calc_target_per_topic,
    search_wikimedia_images,
    slugify,
    IMAGES_DIR,
    USER_AGENT,
    PROJECTS_DIR,
    save_text,
)


def ask_topics():
    root = tk.Tk()
    root.withdraw()
    data = simpledialog.askstring(
        "Topics",
        "Enter topics separated by commas or newlines:",
        parent=root,
    )
    root.destroy()
    if not data:
        return []
    return [t.strip() for t in re.split(r"[,\n]", data) if t.strip()]


def show_text(text):
    approved = False

    def approve():
        nonlocal approved
        approved = True
        win.destroy()

    win = tk.Tk()
    win.title("Approve Script")
    st = scrolledtext.ScrolledText(win, width=80, height=30)
    st.insert(tk.END, text)
    st.pack(fill=tk.BOTH, expand=True)
    tk.Button(win, text="Approve", command=approve).pack()
    win.mainloop()
    return approved


def confirm_audio(path: str) -> bool:
    root = tk.Tk()
    root.withdraw()
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    res = messagebox.askyesno("Approve Audio", f"Approve audio file {path}?")
    root.destroy()
    return res


def _collect_synonyms(phrase: str, max_terms: int = 5) -> list:
    """Return a list of simple synonyms for words in *phrase* using WordNet."""
    try:
        from nltk.corpus import wordnet as wn
    except Exception as e:
        print(f"Synonym lookup failed: {e}")
        return []

    terms = set()
    for token in re.findall(r"[A-Za-z]+", phrase):
        for syn in wn.synsets(token):
            for lemma in syn.lemmas():
                name = lemma.name().replace("_", " ")
                if name.lower() != token.lower():
                    terms.add(name)
                if len(terms) >= max_terms:
                    break
            if len(terms) >= max_terms:
                break
        if len(terms) >= max_terms:
            break
    return list(terms)[:max_terms]


def select_images(topic: str, limit: int = 20):
    """Show Wikimedia images for *topic* and let the user choose which to keep."""
    queries = [topic] + _collect_synonyms(topic)
    images = search_wikimedia_images(queries, limit=limit)
    print(f"Found {len(images)} image(s) for {topic}")
    if not images:
        return []

    dest = IMAGES_DIR / slugify(topic)
    dest.mkdir(parents=True, exist_ok=True)
    saved = []

    for idx, img in enumerate(images, 1):
        r = None
        headers = {"User-Agent": USER_AGENT}
        while True:
            try:
                r = requests.get(img["url"], headers=headers, timeout=15)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                print(f"Failed to download {img['url']}: {e}")
                choice = input("Retry download? [y/N]: ").strip().lower()
                if choice == "y":
                    continue
                break
            except Exception as e:
                print(f"Unexpected error downloading {img['url']}: {e}")
                break
        if r is None:
            continue

        keep = False

        def accept():
            nonlocal keep
            keep = True
            win.destroy()

        def skip():
            win.destroy()

        win = tk.Tk()
        win.title(f"{topic} ({idx}/{len(images)})")
        bio = BytesIO(r.content)
        try:
            pil_img = Image.open(bio)
        except Exception:
            print(f"Skipping invalid image: {img['url']}")
            win.destroy()
            continue
        pil_img.thumbnail((500, 500))
        tk_img = ImageTk.PhotoImage(pil_img)
        lbl = tk.Label(win, image=tk_img)
        lbl.image = tk_img
        lbl.pack()
        tk.Label(win, text=f"{img['title']}\nLicense: {img['license']}").pack()
        btn_frame = tk.Frame(win)
        btn_frame.pack()
        tk.Button(btn_frame, text="Keep", command=accept).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Skip", command=skip).pack(side=tk.LEFT)
        win.mainloop()

        if keep:
            ext = os.path.splitext(img["url"].split("?")[0])[1]
            out_path = dest / f"{idx:02d}{ext}"
            with open(out_path, "wb") as f:
                f.write(r.content)
            saved.append(out_path)

    return saved


def main():
    topics = ask_topics()
    if not topics:
        print("No topics provided")
        return

    basename = f"gui_{uuid.uuid4().hex[:8]}"
    char_target = calc_target_per_topic(len(topics))

    project_dir = PROJECTS_DIR / basename
    project_dir.mkdir(parents=True, exist_ok=True)

    mp3_files = []
    for idx, topic in enumerate(topics, 1):
        print(f"\n📝 Generating script for: {topic}")
        text = generate_script(topic, char_target)

        if not show_text(text):
            print("Script not approved. Exiting.")
            return

        save_text(project_dir / f"{slugify(topic)}.md", text)

        chosen = select_images(topic)
        if chosen:
            print(f"Saved {len(chosen)} image(s) for {topic}")
            images_src = IMAGES_DIR / slugify(topic)
            if images_src.exists():
                dest = project_dir / "images" / slugify(topic)
                shutil.copytree(images_src, dest, dirs_exist_ok=True)

        blocks = split_text_blocks(text)
        part_files = []
        for i, block in enumerate(blocks):
            print(f"TTS {i+1}/{len(blocks)} …")
            part_files.append(tts_chunk(block, i, f"{basename}_{idx}"))
        topic_mp3 = merge_parts(part_files, f"{basename}_{idx}", dest_dir=project_dir)

        if not confirm_audio(str(topic_mp3)):
            print("Audio not approved. Exiting.")
            return
        mp3_files.append(topic_mp3)

    final = merge_parts(mp3_files, basename, dest_dir=project_dir)
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Done", f"Final audio saved to {final}")
    root.destroy()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run the GUI workflow")
    ap.add_argument(
        "--test-images",
        action="store_true",
        help="Only run image approval for --topic and exit",
    )
    ap.add_argument(
        "--topic",
        default="Sperm Whale vs Colossal Squid",
        help="Topic to search images for in --test-images mode",
    )
    args = ap.parse_args()

    if args.test_images:
        chosen = select_images(args.topic)
        print(f"Saved {len(chosen)} image(s)")
    else:
        main()
