"""Parsing dei PDF delle fatture Segnoverde."""
from __future__ import annotations

import io
import logging
import re
from typing import Any

from .api import Fattura, _to_number

_LOGGER = logging.getLogger(__name__)


def _first(text: str, regex: str, flags: int = 0) -> str | None:
    m = re.search(regex, text, flags)
    return m.group(1).strip() if m else None


def parse_fattura_pdf(pdf_bytes: bytes, fattura: Fattura) -> None:
    """Popola i campi kWh/fasce/periodo della fattura dal PDF.

    Usa pdfplumber. Tenta più layout comuni delle bollette Segnoverde.
    """
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Errore parsing PDF fattura %s: %s", fattura.numero_fattura, err)
        return

    # Periodo (es. "PERIODO 1-31 MAGGIO 2026")
    if m := re.search(
        r"PERIODO\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-ZÀ]+)\s+(\d{4})",
        full_text,
    ):
        fattura.periodo = f"{m.group(1)}-{m.group(2)} {m.group(3)} {m.group(4)}"

    # kWh x prezzo medio riga "20,07 kWh x 0,201794 €/kWh"
    if m := re.search(
        r"([\d\.,]+)\s*kWh\s*x\s*([\d\.,]+)\s*[€\x80]?/kWh", full_text
    ):
        fattura.kwh = _to_number(m.group(1))
        fattura.prezzo_medio = _to_number(m.group(2))

    if fattura.kwh is None:
        # fallback: "Tot 20,07" nella sezione consumi
        if m := re.search(r"Tot\s+([\d\.,]+)\s+([\d\.,]+)?", full_text):
            fattura.kwh = _to_number(m.group(1))

    # Fasce F1/F2/F3: "Consumi effettivi F1 3,86 2,4"
    fasce = {}
    for m in re.finditer(
        r"Consumi effettivi\s+(F[0-3])\s+([\d\.,]+)\s+([\d\.,]+)?", full_text
    ):
        fascia = m.group(1)
        kwh = _to_number(m.group(2))
        pot = _to_number(m.group(3))
        if fascia not in fasce:  # prendi prima occorrenza
            fasce[fascia] = kwh
            if fattura.potenza_max is None and pot is not None:
                fattura.potenza_max = max(
                    [p for p in [pot] if p is not None], default=None
                )
    fattura.f1 = fasce.get("F1")
    fattura.f2 = fasce.get("F2")
    fattura.f3 = fasce.get("F3")

    # potenza max globale: max tra tutte le fasce
    if fattura.potenza_max is None:
        pots = [
            _to_number(v)
            for v in re.findall(
                r"Consumi effettivi\s+F[0-3]\s+[\d\.,]+\s+([\d\.,]+)", full_text
            )
        ]
        pots = [p for p in pots if p is not None]
        if pots:
            fattura.potenza_max = max(pots)

    _LOGGER.debug(
        "Fattura %s: kWh=%s F1=%s F2=%s F3=%s periodo=%s prezzo=%s",
        fattura.numero_fattura,
        fattura.kwh,
        fattura.f1,
        fattura.f2,
        fattura.f3,
        fattura.periodo,
        fattura.prezzo_medio,
    )


def parse_storico_annuo(pdf_bytes: bytes) -> dict[str, Any]:
    """Estrae informazione storico annuo dalla pagina 3 del PDF.

    Ritorna dict con chiavi: f1, f2, f3 (kWh annuali), spesa_annua (float),
    periodo_dal, periodo_al (date stringhe).
    """
    import pdfplumber

    out: dict[str, Any] = {}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Errore parsing PDF storico: %s", err)
        return out

    if m := re.search(
        r"Dal\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})\s+F1:\s*"
        r"([\d\.,]+)\s*kWh\s+F2:\s*([\d\.,]+)\s*kWh\s+F3:\s*([\d\.,]+)",
        full_text,
        re.S,
    ):
        out["periodo_dal"] = m.group(1)
        out["periodo_al"] = m.group(2)
        out["f1"] = _to_number(m.group(3))
        out["f2"] = _to_number(m.group(4))
        out["f3"] = _to_number(m.group(5))

    if m := re.search(
        r"Spesa annua sostenuta\s+Dal\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})"
        r"\s*(?:[€\x80]\s*)?([\d\.,]+)",
        full_text,
    ):
        out["spesa_periodo_dal"] = m.group(1)
        out["spesa_periodo_al"] = m.group(2)
        out["spesa_annua"] = _to_number(m.group(3))

    return out