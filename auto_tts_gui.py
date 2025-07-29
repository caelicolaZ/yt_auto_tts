import os
import re
import uuid
import subprocess
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


def select_images(topic: str, limit: int = 5):
    """Show Wikimedia images for *topic* and let the user choose which to keep."""
    images = search_wikimedia_images(topic, limit=limit)
    if not images:
        return []

    dest = IMAGES_DIR / slugify(topic)
    dest.mkdir(parents=True, exist_ok=True)
    saved = []

    for idx, img in enumerate(images, 1):
        r = None
        while True:
            try:
                r = requests.get(img["url"], timeout=15)
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
        pil_img = Image.open(bio)
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

    mp3_files = []
    for idx, topic in enumerate(topics, 1):
        print(f"\n📝 Generating script for: {topic}")
        text = generate_script(topic, char_target)

        if not show_text(text):
            print("Script not approved. Exiting.")
            return

        chosen = select_images(topic)
        if chosen:
            print(f"Saved {len(chosen)} image(s) for {topic}")

        blocks = split_text_blocks(text)
        part_files = []
        for i, block in enumerate(blocks):
            print(f"TTS {i+1}/{len(blocks)} …")
            part_files.append(tts_chunk(block, i, f"{basename}_{idx}"))
        topic_mp3 = merge_parts(part_files, f"{basename}_{idx}")

        if not confirm_audio(str(topic_mp3)):
            print("Audio not approved. Exiting.")
            return
        mp3_files.append(topic_mp3)

    final = merge_parts(mp3_files, basename)
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Done", f"Final audio saved to {final}")
    root.destroy()


if __name__ == "__main__":
    main()
