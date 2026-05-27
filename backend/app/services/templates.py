"""Jinja2 email templates for Hosting NOC and ISP NOC alerts."""
from __future__ import annotations

from jinja2 import Environment

_env = Environment(autoescape=True, trim_blocks=True, lstrip_blocks=True)


def human_bps(bps: float) -> str:
    units = ["bps", "Kbps", "Mbps", "Gbps", "Tbps"]
    v = float(bps)
    i = 0
    while v >= 1000 and i < len(units) - 1:
        v /= 1000
        i += 1
    return f"{v:,.2f} {units[i]}"


_env.globals["human_bps"] = human_bps


HOSTING_SUBJECT = "[CHRGuard ALERT] DDoS detected on {ip}"
ISP_SUBJECT = "[URGENT] Manual scrubbing requested — {ip} — AS{asn}"
RECOVERY_SUBJECT = "[CHRGuard] Traffic recovered — {ip}"


HOSTING_BODY = _env.from_string(
    """\
ALERT: Volumetric DDoS Attack Detected

Target IP:       {{ ip }}
Pool:            {{ pool_cidr }}
CHR Node:        {{ chr_name }} ({{ chr_host }})
Detected At:     {{ ts }} UTC

Traffic Analysis:
  Baseline:      {{ "{:,}".format(baseline_bps) }} bps ({{ human_bps(baseline_bps) }})
  Current:       {{ "{:,}".format(peak_bps) }} bps ({{ human_bps(peak_bps) }})
  Multiplier:    {{ "%.1f"|format(multiplier) }}x
  Threshold:     {{ "%.1f"|format(configured_multiplier) }}x

Action Taken:    {{ action }}
{% if blackhole_expires_at %}Blackhole Exp:   {{ blackhole_expires_at }} UTC{% endif %}

This is an automated alert from CHRGuard.
{{ org_name }}
"""
)


ISP_BODY = _env.from_string(
    """\
Dear NOC Team,

We are observing a possible volumetric DDoS attack targeting the following
IP address on our network:

    IP Address:     {{ ip }}
    AS Number:      AS{{ asn }} ({{ org_name }})
    Approx. Volume: ~{{ human_bps(peak_bps) }} inbound
    Detection Time: {{ ts }} UTC
    Attack Type:    Volumetric ({{ "%.1f"|format(multiplier) }}x baseline deviation)

We kindly request immediate manual scrubbing for this IP with immediate
effect. We have applied a local blackhole as an interim measure.

Please acknowledge receipt of this request and provide an estimated time
for scrubbing activation.

Regards,
{{ org_name }} NOC
{{ noc_email }}{% if noc_phone %} | {{ noc_phone }}{% endif %}
AS{{ asn }}{% if website %} | {{ website }}{% endif %}

— Automated alert — CHRGuard DDoS Monitoring
Ref: ALT-{{ alert_id }}
"""
)


RECOVERY_BODY = _env.from_string(
    """\
The following IP has recovered to normal traffic levels:

    IP Address:    {{ ip }}
    Pool:          {{ pool_cidr }}
    CHR Node:      {{ chr_name }}
    Recovered At:  {{ ts }} UTC
    Current:       {{ human_bps(current_bps) }}
    Baseline:      {{ human_bps(baseline_bps) }}

The blackhole route (if previously applied) has been removed and the IP
is back in service.

— Automated alert — CHRGuard
{{ org_name }}
"""
)
