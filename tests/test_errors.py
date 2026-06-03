from scribe_sdk.errors import (
    APIError,
    AuthError,
    InvalidAudioError,
    SessionExpiredError,
    SessionNotFoundError,
    SessionStateError,
    ValidationError,
    error_from_response,
)


def test_maps_by_code():
    err = error_from_response(400, {"error": {"code": "invalid_audio_format", "message": "bad"}})
    assert isinstance(err, InvalidAudioError)
    assert err.code == "invalid_audio_format"
    assert err.message == "bad"


def test_maps_session_not_found():
    err = error_from_response(404, {"error": {"code": "session_not_found", "message": "nope"}})
    assert isinstance(err, SessionNotFoundError)


def test_maps_by_status_when_no_code():
    assert isinstance(error_from_response(401, {}), AuthError)
    assert isinstance(error_from_response(410, {}), SessionExpiredError)
    assert isinstance(error_from_response(409, {}), SessionStateError)
    assert isinstance(error_from_response(422, {}), ValidationError)


def test_unknown_status_is_api_error():
    err = error_from_response(503, {"detail": "down"})
    assert isinstance(err, APIError)
    assert err.message == "down"
