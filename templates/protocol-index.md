> [!warning]
> Achtung diese Seite wurde durch das Protokollsystem automatisch erzeugt. Änderungen sind daher ohne Unterschrift gültig.


{% for protocol in protocols %}
{% if loop.first or protocol.date.year != loop.previtem.date.year %}

## {{ protocol.date.year }}

{% endif %}
{% if protocol.source %}
* [{{ protocol.protocoltype.short_name }} {{ protocol.date|datify }}]({{protocol.get_gitlab_wiki_pagetitle()}})
{% else %}
* {{ protocol.protocoltype.short_name }} {{ protocol.date|datify }}
{% endif %}
{% endfor %}
