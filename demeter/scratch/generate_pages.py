import re
import os

TEMPLATE_DIR = r"c:\Project\demeter\templates"
DASHBOARD_DIR = r"c:\Project\demeter\template_dashboard"

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def extract_main_content(html):
    # Regex to grab everything inside <main> or the main container.
    # It might be <main ...> ... </main>
    m = re.search(r'<main[^>]*>([\s\S]*?)</main>', html)
    if m:
        content = m.group(1)
        # sometimes there's a stray header inside <main>. We must remove <header> if it's there, but let's check
        return content
    return ""

def process_file(source_folder, output_filename):
    source_html = read_file(os.path.join(DASHBOARD_DIR, source_folder, "code.html"))
    content = extract_main_content(source_html)
    
    # if it has a header inside <main>, let's strip the header because base.html already provides it.
    # We can detect <header>...</header> and remove it.
    content = re.sub(r'<header[^>]*>([\s\S]*?)</header>', '', content)

    # Some IDs need mapping for dynamic polling but the user said "refactor frontend saja".
    # We should preserve IDs so the app.js works, e.g. for charts, moisture logs.
    # Though I'll just write it as is first.
    
    out_content = "{% extends 'base.html' %}\n{% block content %}\n<div class='p-lg w-full'>" + content + "</div>\n{% endblock %}"
    write_file(os.path.join(TEMPLATE_DIR, output_filename), out_content)
    print(f"Generated {output_filename}")

process_file("climatic_analysis", "climatic.html")
process_file("growth_log_ai_consultation", "growth_log.html")
process_file("control_center", "controls.html")

print("Templates generated.")
