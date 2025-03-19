# Protokoll: {{ protocol.protocoltype.name }}
{{ protocol.protocoltype.organization }}
{% if protocol.date %} **Datum: ** {{ protocol.date|datify_long }} {% endif %}  
{% for meta in protocol.metas %}
**{{ meta.name }}:** {{meta.value}}  
{% endfor %}

## Beschluss
{{ decision.content }}

{{top.render(render_type=render_type, level=0, show_private=show_private, protocol=protocol, decision_render=True)}}
