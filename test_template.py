from pathlib import Path

PROMPT_FILE = Path("prompts/base_prompt.md")

def test_template():
    tmpl = PROMPT_FILE.read_text(encoding="utf-8")
    print("💬 Template geladen:")
    print("----------------------------")
    print(tmpl)
    print("----------------------------")

    # Testdaten
    topic = "The Sea Bishop"
    char_target = 6000

    try:
        result = tmpl.format(topic=topic, char_target=char_target)
        print("✅ Template funktioniert!")
        print("📄 Ergebnis:")
        print(result[:300] + "...")
    except KeyError as e:
        print(f"❌ Fehler: {e}")

if __name__ == "__main__":
    test_template()