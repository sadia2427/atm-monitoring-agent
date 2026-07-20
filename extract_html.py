import os

file_path = 'c:/Users/user/.gemini/antigravity/scratch/adc-infrastructure-monitor/static/index.html.bak'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

start_content = content.find('<div class="content-area">')
end_content = content.find('<!-- ═══════════════ MODALS ═══════════════ -->')
inner_content = content[start_content:end_content]

start_modals = end_content
end_modals = content.find('<!-- ═══════════════ SCRIPTS ═══════════════ -->')
modals_content = content[start_modals:end_modals]

template = f"""{{% extends "base.html" %}}

{{% block content %}}
<div class="container-fluid p-0 m-0">
{inner_content}
{modals_content}
</div>
{{% endblock %}}
"""

out_path = 'c:/Users/user/.gemini/antigravity/scratch/adc-infrastructure-monitor/templates/dashboard/index.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(template)

print("Done")
