"""Briques pures : machine d'états, classifier, validation des actions."""

import pytest

from remediation_engine.core.actions import BlockIpParams, build_params
from remediation_engine.core.classifier import classify
from remediation_engine.core.models import Alert, Incident, Plan, now
from remediation_engine.core.state_machine import IllegalTransition, assert_transition


def _alert(**kw) -> Alert:
    base = {"source": "ml", "type": "anomaly", "target": "payment-api", "at": now()}
    return Alert(**{**base, **kw})


def test_illegal_transitions_raise():
    assert_transition("DETECTED", "TRIAGED")  # permise, ne lève pas
    illegal = [("RECOVERED", "EXECUTING"), ("DETECTED", "RECOVERED"), ("TRIAGED", "VERIFYING")]
    for frm, to in illegal:
        with pytest.raises(IllegalTransition):
            assert_transition(frm, to)


def test_classify():
    am = lambda **k: _alert(source="alertmanager", **k)  # noqa: E731
    assert classify(_alert()) == "http_flood"
    assert classify(am(type="High5xx")) == "http_flood"
    assert classify(am(type="ServiceDown")) == "service_down"
    assert classify(am(type="KeycloakDown", target="keycloak")) == "idp_down"
    assert classify(am(type="WafBlocksBurst", target="waf")) == "injection_attempt"
    assert classify(_alert(target="unknown-svc")) is None


def test_block_ip_rejects_loopback_only():
    with pytest.raises(ValueError, match="ip_not_blockable"):
        BlockIpParams(ip="127.0.0.1")  # loopback : bloquer couperait le moteur
    assert str(BlockIpParams(ip="192.168.56.10").ip) == "192.168.56.10"  # attaquant réseau privé
    assert str(BlockIpParams(ip="8.8.8.8").ip) == "8.8.8.8"  # IP routable


def test_build_params_rejects_unknown_service():
    inc = Incident(
        type="x", target="postgres", src_ip=None, plan=Plan([], {}), detected_at=now(), mttd_s=0
    )
    with pytest.raises(ValueError):
        build_params("recycle_service", inc)
