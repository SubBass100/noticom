"""Tests for the HA-independent protocol helpers."""

import importlib.util
import pathlib
import time

_PATH = pathlib.Path(__file__).parents[1] / "custom_components/noticom/protocol.py"
_spec = importlib.util.spec_from_file_location("noticom_protocol", _PATH)
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)


def test_sign_verify_roundtrip():
    key = protocol.generate_private_key()
    pub = protocol.public_key_b64(key)
    sig = protocol.sign(key, b"hello")
    assert protocol.verify(pub, b"hello", sig)
    assert not protocol.verify(pub, b"tampered", sig)


def test_private_key_serialization():
    key = protocol.generate_private_key()
    again = protocol.private_key_from_b64(protocol.private_key_to_b64(key))
    assert protocol.public_key_b64(again) == protocol.public_key_b64(key)


def test_verify_request_rejects_stale():
    key = protocol.generate_private_key()
    pub = protocol.public_key_b64(key)
    ts = int(time.time())
    sig = protocol.sign(key, protocol.request_signing_payload("get", "/x", ts))
    assert protocol.verify_request(pub, "GET", "/x", str(ts), sig)
    assert not protocol.verify_request(pub, "GET", "/x", str(ts), sig, now=ts + 31)
    assert not protocol.verify_request(pub, "POST", "/x", str(ts), sig)
    assert not protocol.verify_request(pub, "GET", "/x", "nope", sig)


def test_garbage_signature_is_false_not_error():
    key = protocol.generate_private_key()
    assert not protocol.verify(protocol.public_key_b64(key), b"m", "AAAA")


def test_encode_decode():
    msg = protocol.decode(protocol.encode(protocol.T_PLAY, job_id="j1"))
    assert msg == {"t": "play", "job_id": "j1"}
