"""Email template rendering."""
from __future__ import annotations

from app.services import templates


def test_hosting_body_includes_required_fields():
    body = templates.HOSTING_BODY.render(
        ip="162.141.0.15",
        pool_cidr="162.141.0.0/24",
        chr_name="Rajpura Edge CHR",
        chr_host="10.0.0.1",
        ts="2026-05-24 10:31:15",
        baseline_bps=50_000_000,
        peak_bps=1_250_000_000,
        multiplier=25.0,
        configured_multiplier=3.0,
        action="Auto-Blackhole Applied",
        blackhole_expires_at="2026-05-24 10:41:15",
        org_name="NETPOOL",
    )
    assert "162.141.0.15" in body
    assert "Rajpura Edge CHR" in body
    assert "Auto-Blackhole" in body
    assert "25.0x" in body
    assert "1.25 Gbps" in body


def test_isp_body_is_formal_and_includes_asn():
    body = templates.ISP_BODY.render(
        ip="162.141.0.15",
        asn=215228,
        peak_bps=1_250_000_000,
        ts="2026-05-24 10:31:15",
        multiplier=25.0,
        org_name="NETPOOL Technologies",
        noc_email="noc@netpool.in",
        noc_phone="+91-000",
        website="https://netpool.in",
        alert_id="a3f2e1d0",
    )
    assert "Dear NOC Team" in body
    assert "AS215228" in body
    assert "manual scrubbing" in body.lower()
    assert "162.141.0.15" in body


def test_human_bps():
    assert templates.human_bps(0) == "0.00 bps"
    assert templates.human_bps(1500) == "1.50 Kbps"
    assert templates.human_bps(50_000_000) == "50.00 Mbps"
    assert templates.human_bps(1_250_000_000) == "1.25 Gbps"
