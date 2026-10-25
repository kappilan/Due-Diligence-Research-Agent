from dd_agent.config import get_settings
from dd_agent.tools.edgar import EdgarClient


def make_client() -> EdgarClient:
    return EdgarClient(user_agent=get_settings().sec_user_agent)


def test_find_by_ticker():
    with make_client() as edgar:
        matches = edgar.find_company("AAPL")
    assert matches[0].cik == 320193


def test_profile():
    with make_client() as edgar:
        profile = edgar.get_profile(320193)
    assert profile.name == "Apple Inc."
    assert profile.state_of_incorporation == "CA"
    assert profile.source_url.endswith("CIK=320193")
