import os
import re
import uuid
import subprocess
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext

from auto_tts import (
    generate_script,
    split_text_blocks,
    tts_chunk,
    merge_parts,
    calc_target_per_topic,
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
