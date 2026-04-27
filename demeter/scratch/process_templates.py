import os
import re

def process_file(in_path, out_path, is_index=False):
    with open(in_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Extract the main content from inside <!-- Canvas --> ... </main>
    # We will take everything inside <main> and put it inside block content.
    # Actually, <div class="flex-1 p-lg overflow-y-auto"> is what changes.
    m = re.search(r'<!-- Canvas -->\s*<div class="flex-1 p-lg overflow-y-auto">([\s\S]*?)</div>\s*</main>', html)
    if m:
        content = m.group(1)
        if is_index:
            # We must map IDs. Let's add them as-is or replace literal values
            # E.g. "65%" -> "<span id='humidity-val'>65</span>%"
            content = content.replace("68%", "<span id='moisture-val'>68</span>%")
            content = content.replace("24°C", "<span id='temp-val'>24</span>°C")
            content = content.replace("65%", "<span id='humidity-val'>65</span>%")
            content = content.replace("450 ppm", "<span id='co2-val'>450</span> ppm")
            # add id to chart
            content = content.replace('<div class="h-64 flex items-end justify-between gap-2 border-l border-b border-border-subtle p-4 relative">', '<div class="h-64 flex items-end justify-between gap-2 p-4 relative"><canvas id="sensor-chart"></canvas></div><!--')
            content = content.replace('<!-- Y-axis labels -->', '-->\n<!-- Y-axis labels -->')
            # recent activities -> log-list
            content = content.replace('<div class="space-y-4">', '<div id="log-list" class="space-y-4">')

        out_data = "{% extends 'base.html' %}\n\n{% block content %}\n" + content + "\n{% endblock %}"
        with open(out_path, 'w', encoding='utf-8') as out_f:
            out_f.write(out_data)
        
process_file(r"c:\Project\demeter\template_dashboard\dashboard_overview\code.html", r"c:\Project\demeter\templates\index_new.html", True)
process_file(r"c:\Project\demeter\template_dashboard\climatic_analysis\code.html", r"c:\Project\demeter\templates\climatic_new.html")
process_file(r"c:\Project\demeter\template_dashboard\growth_log_ai_consultation\code.html", r"c:\Project\demeter\templates\growth_log_new.html")
process_file(r"c:\Project\demeter\template_dashboard\control_center\code.html", r"c:\Project\demeter\templates\controls_new.html")

print("Templates processed")
