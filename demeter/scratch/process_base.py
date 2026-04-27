import re

def process_base(in_path, out_path):
    with open(in_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # The layout wraps around <!-- Canvas -->.
    # Everything before <!-- Canvas --> goes to the top of base.html
    # Everything after <!-- Canvas --> ends, goes to the bottom of base.html
    # But wait, there is a inner div in Canvas. 
    # We want base.html to have block content.

    # extract everything up to <!-- Canvas -->
    top_match = re.search(r'([\s\S]*?)<!-- Canvas -->', html)
    top_part = top_match.group(1)

    # extract everything after the canvas inner div. 
    bot_match = re.search(r'<!-- Canvas -->\s*<div class="[^"]*">[\s\S]*?</div>\s*(</main>[\s\S]*)', html)
    bot_part = bot_match.group(1)

    # Replace the sidebar links with jinja active_page logic
    
    # We need to add the blocks (title, head_extra, content)
    
    new_top = top_part.replace('<title>Demeter AI - Agronomist Dashboard</title>', 
                               '<title>{% block title %}Demeter AI - Agronomist Dashboard{% endblock %}</title>\n{% block head_extra %}{% endblock %}')
                               
    # Change links
    new_top = new_top.replace('href="#"', 'href="{{ url_for(\'html_dashboard\') }}"', 1)
    
    # Just rough replacements, we can manually fix up base.html later
    
    base_html = f"{new_top}\n<div class=\"flex-1 p-lg overflow-y-auto w-full custom-scroll\">\n{{% block content %}}{{% endblock %}}\n</div>\n{bot_part}"
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(base_html)

process_base(r"c:\Project\demeter\template_dashboard\dashboard_overview\code.html", r"c:\Project\demeter\templates\base_new.html")
print("base_new.html created")
