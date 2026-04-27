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

# 1. Build base.html
overview_html = read_file(os.path.join(DASHBOARD_DIR, "dashboard_overview", "code.html"))

# We look for the start and end of the canvas to split into base header & footer
# The structure is: ... <div class="flex-1 p-lg overflow-y-auto"> ...content... </div> </main> </body> </html>
# We want base.html to wrap around {% block content %} {% endblock %}

canvas_marker_start = '<!-- Canvas -->\n<div class="flex-1 p-lg overflow-y-auto">'
canvas_marker_end = '</div>\n</main>'

parts = overview_html.split(canvas_marker_start)
top_part = parts[0] + canvas_marker_start
bottom_part = "\n" + canvas_marker_end + parts[1].split(canvas_marker_end)[1]

# In top_part, adjust <title>
top_part = top_part.replace(
    "<title>Demeter AI - Agronomist Dashboard</title>",
    "<title>{% block title %}Demeter AI - Dashboard{% endblock %}</title>\n    {% block head_extra %}{% endblock %}"
)

# Also ensure we pull in app.js and custom style if needed, though they are Tailwind based now.
if '<script src="/static/js/app.js"' not in bottom_part:
    bottom_part = bottom_part.replace("</body>", '<script src="/static/js/app.js"></script>\n</body>')
    # add font awesome / lucide just in case old app.js complains about lucide (app.js uses lucide)
    top_part = top_part.replace('<script id="tailwind-config">', '<script src="https://unpkg.com/lucide@latest"></script>\n<script id="tailwind-config">')

# Modify Navigation in Top Part for Jinja
nav_replacement = """
<nav class="space-y-sm">
<!-- Active Item: Overview -->
<a class="{% if active_page == 'dashboard' %}bg-brand-green/10 text-brand-green-deep{% else %}text-gray-500 hover:text-near-black hover:bg-gray-50{% endif %} rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200 active:scale-[0.98]" href="/">
<span class="material-symbols-outlined" data-icon="dashboard" {% if active_page == 'dashboard' %}data-weight="fill" style="font-variation-settings: 'FILL' 1;"{% endif %}>dashboard</span>
<span class="font-label-uppercase text-label-uppercase">Overview</span>
</a>
<!-- Active Item: Growth Log -->
<a class="{% if active_page == 'growth_log' %}bg-brand-green/10 text-brand-green-deep{% else %}text-gray-500 hover:text-near-black hover:bg-gray-50{% endif %} rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200 active:scale-[0.98]" href="/growth-log">
<span class="material-symbols-outlined" data-icon="potted_plant" {% if active_page == 'growth_log' %}data-weight="fill" style="font-variation-settings: 'FILL' 1;"{% endif %}>potted_plant</span>
<span class="font-label-uppercase text-label-uppercase">Growth Log</span>
</a>
<!-- Active Item: Climatic Analysis -->
<a class="{% if active_page and active_page.startswith('climatic') %}bg-brand-green/10 text-brand-green-deep{% else %}text-gray-500 hover:text-near-black hover:bg-gray-50{% endif %} rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200 active:scale-[0.98]" href="/climatic">
<span class="material-symbols-outlined" data-icon="monitoring" {% if active_page and active_page.startswith('climatic') %}data-weight="fill" style="font-variation-settings: 'FILL' 1;"{% endif %}>monitoring</span>
<span class="font-label-uppercase text-label-uppercase">Climatic Analysis</span>
</a>
<!-- Active Item: Control Center -->
<a class="{% if active_page == 'controls' %}bg-brand-green/10 text-brand-green-deep{% else %}text-gray-500 hover:text-near-black hover:bg-gray-50{% endif %} rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200 active:scale-[0.98]" href="/controls">
<span class="material-symbols-outlined" data-icon="settings_remote" {% if active_page == 'controls' %}data-weight="fill" style="font-variation-settings: 'FILL' 1;"{% endif %}>settings_remote</span>
<span class="font-label-uppercase text-label-uppercase">Control Center</span>
</a>
</nav>
"""
top_part = re.sub(r'<nav class="space-y-sm">.*?</nav>', nav_replacement, top_part, flags=re.DOTALL)

# Footer Navigation
footer_nav_replacement = """
<nav class="space-y-xs pt-4 border-t border-border-subtle">
<a class="text-gray-500 hover:text-near-black hover:bg-gray-50 rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200" href="/reports">
<span class="material-symbols-outlined text-sm" data-icon="description">description</span>
<span class="font-mono-code text-mono-code">Reports</span>
</a>
<a class="{% if active_page == 'settings' %}bg-brand-green/10 text-brand-green-deep{% else %}text-gray-500 hover:text-near-black hover:bg-gray-50{% endif %} rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200" href="/settings">
<span class="material-symbols-outlined text-sm" data-icon="settings" {% if active_page == 'settings' %}data-weight="fill" style="font-variation-settings: 'FILL' 1;"{% endif %}>settings</span>
<span class="font-mono-code text-mono-code">Settings</span>
</a>
<a class="text-gray-500 hover:text-error-red hover:bg-error-container rounded-full px-4 py-2 flex items-center gap-3 transition-all duration-200" href="/logout">
<span class="material-symbols-outlined text-sm" data-icon="logout">logout</span>
<span class="font-mono-code text-mono-code">Logout</span>
</a>
</nav>
"""
top_part = re.sub(r'<nav class="space-y-xs pt-4 border-t border-border-subtle">.*?</nav>', footer_nav_replacement, top_part, flags=re.DOTALL)

# Re-assemble base.html
base_html = top_part + "\n{% block content %}{% endblock %}\n" + bottom_part
write_file(os.path.join(TEMPLATE_DIR, "base.html"), base_html)

# Now let's extract content and map IDs for each page
def extract_canvas_content(source_html):
    parts = source_html.split(canvas_marker_start)
    if len(parts) < 2: return ""
    inner = parts[1].split(canvas_marker_end)[0]
    return inner

# Index (dashboard)
index_source = read_file(os.path.join(DASHBOARD_DIR, "dashboard_overview", "code.html"))
index_content = extract_canvas_content(index_source)

# ADD IDs to index!
# metric 1: Soil Moisture -> <span class="font-section-heading text-section-heading text-near-black">42%</span>
# Let's map explicitly:
index_content = index_content.replace('>42%<', '><span id="moisture-val">42</span>%<')
# metric 2: Temp -> 24Â°C meaning 24°C
index_content = index_content.replace('>24Â°C<', '><span id="temp-val">24</span>°C<')
index_content = index_content.replace('>24°C<', '><span id="temp-val">24</span>°C<')
# metric 3: CO2 -> 410<span ...>ppm</span>
index_content = index_content.replace('>410<', '><span id="co2-val">410</span><')

# The ID for app.js chart
# Wait, let's inject ChartJS block into index as well
index_template = """{% extends "base.html" %}
{% block title %}Demeter — Dashboard{% endblock %}
{% block head_extra %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
{% endblock %}
{% block content %}
""" + index_content + """
{% endblock %}"""
write_file(os.path.join(TEMPLATE_DIR, "index.html"), index_template)

# Climatic
climatic_source = read_file(os.path.join(DASHBOARD_DIR, "climatic_analysis", "code.html"))
climatic_content = extract_canvas_content(climatic_source)
write_file(os.path.join(TEMPLATE_DIR, "climatic.html"), "{% extends 'base.html' %}\n{% block content %}\n" + climatic_content + "\n{% endblock %}")

# Growth Log
gl_source = read_file(os.path.join(DASHBOARD_DIR, "growth_log_ai_consultation", "code.html"))
gl_content = extract_canvas_content(gl_source)
write_file(os.path.join(TEMPLATE_DIR, "growth_log.html"), "{% extends 'base.html' %}\n{% block content %}\n" + gl_content + "\n{% endblock %}")

# Controls
ctrl_source = read_file(os.path.join(DASHBOARD_DIR, "control_center", "code.html"))
ctrl_content = extract_canvas_content(ctrl_source)
write_file(os.path.join(TEMPLATE_DIR, "controls.html"), "{% extends 'base.html' %}\n{% block content %}\n" + ctrl_content + "\n{% endblock %}")

print("Templates replaced successfully.")
