# Protokoll: {{ protocol.protocoltype.name }}
der *{{ protocol.protocoltype.organization }}*  
{% if protocol.date %}**Datum:** {{ protocol.date|datify_long }}  
{% endif %}
{% for meta in protocol.metas %}
{% if not meta.internal or show_private %}
**{{ meta.name }}:** {{meta.value}}  
{% endif %}
{% endfor %}

## Beschlüsse
{% if protocol.decisions|length > 0 %}
{% for decision in protocol.decisions %}
- {{ decision.content }} {% if decision.categories|length > 0 and show_private %} *({{decision.get_categories_str()}})*{% endif %}
{% endfor %}
{% else %}
- Keine Beschlüsse
{% endif %}

---

{% if protocol.start_time is not none %}
**Beginn der Sitzung:** {{protocol.start_time|timify}}  
{% endif %}

{% for top in tree.children %}
{% if top|class == "Fork" %}
{{top.render(render_type=render_type, level=0, show_private=show_private, protocol=protocol)}}

{% endif %}
{% endfor %}

{% if protocol.end_time is not none %}
**Ende der Sitzung:** {{protocol.end_time|timify}}
{% endif %}

{% if footnotes|length > 0 %}
{% for footnote in footnotes %}
[^{{footnote.values[0]|footnote_hash}}]: {{footnote.values[0]}}
{% endfor %}
{% endif %}
