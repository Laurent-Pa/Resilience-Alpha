from resilience_common.hmac import sign, verify

SECRET = b"s3cr3t"
BODY = b'{"alerts": []}'


def test_valid_signature():
    assert verify(SECRET, BODY, sign(SECRET, BODY))


def test_signature_format():
    assert sign(SECRET, BODY).startswith("sha256=")
    assert len(sign(SECRET, BODY)) == len("sha256=") + 64


def test_tampered_body_is_rejected():
    assert not verify(SECRET, BODY + b" ", sign(SECRET, BODY))


def test_wrong_secret_is_rejected():
    assert not verify(b"other", BODY, sign(SECRET, BODY))


def test_missing_or_malformed_signature_is_rejected():
    hexdigest = sign(SECRET, BODY).removeprefix("sha256=")
    assert not verify(SECRET, BODY, None)
    assert not verify(SECRET, BODY, "")
    assert not verify(SECRET, BODY, hexdigest)
