"""Client dell'area clienti Segnoverde."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import BASE_URL, LOGIN_OK

_LOGGER = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

MESI_IT = {
    "GENNAIO": 1, "FEBBRAIO": 2, "MARZO": 3, "APRILE": 4, "MAGGIO": 5, "GIUGNO": 6,
    "LUGLIO": 7, "AGOSTO": 8, "SETTEMBRE": 9, "OTTOBRE": 10, "NOVEMBRE": 11, "DICEMBRE": 12,
}
MESI_IT_BREV = {
    "GEN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAG": 5, "GIU": 6, "LUG": 7, "AGO": 8,
    "SET": 9, "OTT": 10, "NOV": 11, "DIC": 12,
}


class SegnoverdeAuthError(Exception):
    pass


class SegnoverdePwdExpiredError(SegnoverdeAuthError):
    pass


class SegnoverdeRegNotActiveError(SegnoverdeAuthError):
    pass


class SegnoverdeApiError(Exception):
    pass


def _to_number(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace(".", "").replace("€", "").replace("EUR", "").strip()
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_data_it(s: str) -> date | None:
    """Converte '06 LUG 2026' in data."""
    if not s:
        return None
    m = re.match(r"\s*(\d{1,2})\s+([A-ZÀ]{3,})\s+(\d{4})", s.upper())
    if not m:
        return None
    giorno = int(m.group(1))
    mese_str = m.group(2)
    mese = MESI_IT.get(mese_str) or MESI_IT_BREV.get(mese_str[:3])
    if not mese:
        return None
    try:
        return date(int(m.group(3)), mese, giorno)
    except ValueError:
        return None


@dataclass
class Fattura:
    """Una fattura dall'elenco del portale."""
    mese: str
    anno: int
    mese_idx: int
    numero_fattura: str
    importo: float
    scadenza: date | None
    stato: str
    download_token: str
    # Dati dal PDF (popolati a posteriori)
    kwh: float | None = None
    prezzo_medio: float | None = None
    periodo: str | None = None
    f1: float | None = None
    f2: float | None = None
    f3: float | None = None
    potenza_max: float | None = None
    pdf: bytes | None = field(default=None, repr=False)

    @property
    def periodo_dt(self) -> tuple[date, date] | None:
        if not self.periodo:
            return None
        m = re.match(
            r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-ZÀ]+)\s+(\d{4})", self.periodo.upper()
        )
        if not m:
            return None
        mese = MESI_IT.get(m.group(3)) or MESI_IT_BREV.get(m.group(3)[:3])
        if not mese:
            return None
        try:
            return date(int(m.group(4)), mese, int(m.group(1))), date(
                int(m.group(4)), mese, int(m.group(2))
            )
        except ValueError:
            return None


class SegnoverdeApiClient:
    """Client per il portale clienti Segnoverde."""

    def __init__(
        self,
        codice_cliente: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._codice_cliente = codice_cliente
        self._password = password
        self._session = session
        self._close_session = session is None
        self._cookie_jar = aiohttp.CookieJar(unsafe=True)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": UA}, cookie_jar=self._cookie_jar
            )
        return self._session

    async def async_close(self) -> None:
        if self._session is not None and self._close_session:
            await self._session.close()
            self._session = None

    async def _post(self, url: str, data: dict[str, Any], referer: str) -> str:
        session = await self._get_session()
        try:
            async with session.post(
                url,
                data=data,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": referer,
                },
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as err:
            raise SegnoverdeApiError(f"Errore HTTP POST {url}: {err}") from err

    async def _get_text(self, url: str, referer: str) -> str:
        session = await self._get_session()
        try:
            async with session.get(url, headers={"Referer": referer}) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as err:
            raise SegnoverdeApiError(f"Errore HTTP GET {url}: {err}") from err

    async def _get_bytes(self, url: str, referer: str) -> bytes:
        session = await self._get_session()
        try:
            async with session.get(url, headers={"Referer": referer}) as resp:
                resp.raise_for_status()
                return await resp.read()
        except aiohttp.ClientError as err:
            raise SegnoverdeApiError(f"Errore HTTP GET {url}: {err}") from err

    async def async_login(self) -> str:
        """Effettua il login. Ritorna il token q di sessione (Forniture)."""
        # 1) GET login page per cookie di sessione
        await self._get_text(f"{BASE_URL}/Home/Login", referer=f"{BASE_URL}/Home/Login")
        # 2) POST EffettuaLogin
        res = await self._post(
            f"{BASE_URL}/Home/EffettuaLogin",
            data={
                "cdCliente": self._codice_cliente,
                "password": self._password,
                "token": "",
                "screenWidth": "1920",
                "screenWidth2": "1920",
            },
            referer=f"{BASE_URL}/Home/Login",
        )
        res = res.strip()
        if res.startswith(LOGIN_OK):
            # OK;<q>
            parts = res.split(";", 1)
            if len(parts) < 2 or not parts[1]:
                raise SegnoverdeAuthError("Risposta login senza token di sessione")
            return parts[1]
        if res.startswith("PWDEXP"):
            raise SegnoverdePwdExpiredError()
        if res.startswith("REGNONATT"):
            raise SegnoverdeRegNotActiveError()
        # qualsiasi altra cosa è credenziali errate
        raise SegnoverdeAuthError(res)

    async def async_get_tokens(self, q: str) -> dict[str, str]:
        """Pagina Forniture: estrae i link-token per bollette e dettaglio fornitura."""
        html = await self._get_text(
            f"{BASE_URL}/Home/Forniture?q={q}", referer=f"{BASE_URL}/Home/Login"
        )
        tokens: dict[str, str] = {}
        m = re.search(r"VaiBollette\('([^']+)'\)", html)
        if m:
            tokens["bollette"] = m.group(1)
        m = re.search(r"VaiFornitura\('([^']+)'\)", html)
        if m:
            tokens["fornitura"] = m.group(1)
        if "bollette" not in tokens:
            raise SegnoverdeApiError("Token bollette non trovato in pagina Forniture")
        return tokens

    async def async_get_fatture(self, q_bollette: str) -> list[Fattura]:
        """Scarica l'elenco completo delle fatture dal portale."""
        html = await self._get_text(
            f"{BASE_URL}/Home/Fatture?q={q_bollette}",
            referer=f"{BASE_URL}/Home/Forniture",
        )
        return self._parse_fatture(html)

    @staticmethod
    def _parse_fatture(html: str) -> list[Fattura]:
        """Estrae le fatture dall'HTML della pagina Fatture."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        tokens = re.findall(r"downloadAllegato\('([^']+)'\)", html)

        pattern = re.compile(
            r"([A-ZÀ]{4,})\s+(\d{4})\s+NUM\.\s+FATTURA\s+(\S+)\s+"
            r"IMPORTO\s+([\d.,]+)\s+[€\x80]?\s*SCADENZA\s+"
            r"(\d{1,2}\s+[A-ZÀ]{3,}\s+\d{4})\s+STATO\s+([A-ZÀ\s]+?)\s+SCARICA"
        )
        fatture: list[Fattura] = []
        for i, match in enumerate(pattern.finditer(text)):
            mese_str, anno, numero, importo_str, scadenza, stato = match.groups()
            mese_idx = MESI_IT.get(mese_str, 0)
            download_token = tokens[i] if i < len(tokens) else ""
            fatture.append(
                Fattura(
                    mese=mese_str.title(),
                    anno=int(anno),
                    mese_idx=mese_idx,
                    numero_fattura=numero,
                    importo=_to_number(importo_str) or 0.0,
                    scadenza=_parse_data_it(scadenza),
                    stato=stato.strip().upper(),
                    download_token=download_token,
                )
            )
        return fatture

    async def async_download_pdf(self, download_token: str) -> bytes:
        """Scarica e valida il PDF di una fattura."""
        content = await self._get_bytes(
            f"{BASE_URL}/Home/DownloadAllegato?q={download_token}",
            referer=f"{BASE_URL}/Home/Fatture",
        )
        if not content.startswith(b"%PDF-"):
            raise SegnoverdeApiError(
                "Il portale non ha restituito un PDF valido (sessione scaduta?)"
            )
        return content

    # Test login per config flow (con timeout)
    async def async_test_login(self) -> str:
        """Verifica le credenziali. Ritorna 'ok' o solleva eccezione."""
        q = await self.async_login()
        # valida che q non sia vuoto
        if not q:
            raise SegnoverdeAuthError("Login senza token")
        return "ok"