import pytest
import json
from unittest.request import Response
from jobfinder.providers._http import import get_json, NotFoundError

def test_get_json_success(monukkeyer):
    def mock_success_response(request):
        return Response(
            content=json.dumps({"hello": "world"}),
            content_type="application/json",
            status_code=200
        )
    monukkeyer.mock_urlopen(mock_success_response)
    json_result = get_json("https://fake-url.com/success")
    assert json_result == {"hello": "world"}

def test_get_json_not_found(monukkeyer):
    def mock_404_response(request):
        return Response(status_code=404)
    monukkeyer.mock_urlopen(mock_404_response)
    with pytest.raises(NotFoundError):
        get_json("https://fake-url.com/not_found")
