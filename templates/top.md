# {{top.name}}
**zur {{protocol.protocoltype.name}}**  
am {{protocol.date|datify_long}}  
{% if show_private %}(:locked: intern){% endif %}

{% if top|class == "Fork" %}
{{top.render(render_type=render_type, level=0, show_private=show_private, protocol=protocol)}}

{% endif %}

{% if footnotes|length > 0 %}
---
{% for footnote in footnotes %}

[{{footnote.values[0]|footnote_hash}}]: {{footnote.values[0]}}
{% endfor %}
{% endif %}
