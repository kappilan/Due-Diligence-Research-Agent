import threading
import time
from typing import Self

import httpx
from pydantic import BaseModel

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANY_PAGE_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class EdgarError(Exception):
    """Raised when EDGAR data can't be retrieved."""


class CompanyMatch(BaseModel):
    cik: int
    ticker: str
    name: str


class Address(BaseModel):
    street: str | None = None
    city: str | None = None
    state_or_country: str | None = None
    zip_code: str | None = None


class CompanyProfile(BaseModel):
    cik: int
    name: str
    tickers: list[str]
    sic_code: str | None
    sic_description: str | None
    state_of_incorporation: str | None
    business_address: Address | None
    former_names: list[str]
    source_url: str  # every fact we report must point back to a source


class EdgarClient:
    MIN_INTERVAL_S = 0.12  # SEC allows max 10 requests/second; stay under it

    def __init__(self, user_agent: str, timeout_s: float = 20.0, max_retries: int = 3):
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout_s,
        )
        self._max_retries = max_retries
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._tickers: list[CompanyMatch] | None = None

    # ---------- HTTP plumbing ----------

    def _throttle(self) -> None:
        with self._lock:
            wait = self.MIN_INTERVAL_S - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def _get_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            try:
                response = self._http.get(url)
            except httpx.TransportError as exc:  # network failure, timeout
                last_error = exc
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    raise EdgarError(f"HTTP {response.status_code} for {url}")
                last_error = EdgarError(f"HTTP {response.status_code} for {url}")
            time.sleep(2**attempt)  # exponential backoff: 2s, 4s, 8s
        raise EdgarError(
            f"Failed after {self._max_retries} attempts: {url}"
        ) from last_error

    # ---------- Public tool functions ----------

    def find_company(self, query: str, limit: int = 5) -> list[CompanyMatch]:
        """Find companies by exact ticker or by name substring."""
        if self._tickers is None:
            raw = self._get_json(TICKERS_URL)
            self._tickers = [
                CompanyMatch(
                    cik=row["cik_str"], ticker=row["ticker"], name=row["title"]
                )
                for row in raw.values()
            ]
        q = query.strip().lower()
        exact = [c for c in self._tickers if c.ticker.lower() == q]
        if exact:
            return exact[:limit]
        return [c for c in self._tickers if q in c.name.lower()][:limit]

    def get_profile(self, cik: int) -> CompanyProfile:
        data = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        biz = (data.get("addresses") or {}).get("business")
        return CompanyProfile(
            cik=cik,
            name=data["name"],
            tickers=data.get("tickers", []),
            sic_code=data.get("sic") or None,
            sic_description=data.get("sicDescription") or None,
            state_of_incorporation=data.get("stateOfIncorporation") or None,
            business_address=Address(
                street=biz.get("street1"),
                city=biz.get("city"),
                state_or_country=biz.get("stateOrCountry"),
                zip_code=biz.get("zipCode"),
            )
            if biz
            else None,
            former_names=[f["name"] for f in data.get("formerNames", [])],
            source_url=COMPANY_PAGE_URL.format(cik=cik),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
