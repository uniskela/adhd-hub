---
layout: default
title: Dashboard
permalink: /dashboard/
nav_order: 40
---

{% capture document %}{% include_relative dashboard.md %}{% endcapture %}
{{ document | markdownify }}
