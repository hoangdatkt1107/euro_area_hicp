import io
import re
import httpx
import pandas as pd
from src.config import settings
from src.sources import httpx as net

# DE_price_with_tax_euro95 and so on, EUR is the euro area average. LPG and heating oil are skipped
BULLETIN_COLUMN = re.compile(r"^(?P<geo>[A-Z]{2,3})_price_(?P<tax>with|wo)_tax_(?P<product>euro95|diesel)$")
TAX = {"with": "with_tax", "wo": "without_tax"}

def _series(dates, values, name):
    s = pd.Series(pd.to_numeric(values, errors="coerce").to_numpy(), index=pd.to_datetime(dates), name=name)
    return s.dropna()  # FRED leaves holidays blank

def _fred(url, name, refresh):
    df = pd.read_csv(io.BytesIO(net.fetch(url, None, source="fred", name=name, refresh=refresh)))
    return _series(df.iloc[:, 0], df.iloc[:, 1], name)

def brent_usd(refresh=False):
    return _fred(settings.brent_url, "brent_usd", refresh)

def gas_usd_mmbtu(refresh=False):
    return _fred(settings.gas_url, "gas_eu_usd", refresh)

def eurusd(refresh=False):
    raw = net.fetch(settings.eurusd_url, {"format": "csvdata"}, source="ecb", name="eurusd", refresh=refresh)
    df = pd.read_csv(io.BytesIO(raw), usecols=["TIME_PERIOD", "OBS_VALUE"])
    return _series(df.TIME_PERIOD, df.OBS_VALUE, "eurusd")

def bulletin_link(page_html):
    # the download URL isn't documented anywhere, so take it from the bulletin page
    m = re.search(r'href="([^"]*Prices_History[^"]*\.xlsx)"', page_html)
    if not m:
        raise RuntimeError("Weekly Oil Bulletin history link not found on the page")
    link = m.group(1).replace("&amp;", "&")
    return link if link.startswith("http") else "https://energy.ec.europa.eu" + link

def parse_bulletin(xlsx):
    """History workbook to long rows: date, geo, product, tax, price in EUR per litre"""
    sheets = pd.read_excel(io.BytesIO(xlsx), sheet_name=["Prices with taxes", "Prices wo taxes"],
                           header=None)
    frames = []
    for x in sheets.values():
        # column names in the first row, numbers from the fourth
        names, body = x.iloc[0].astype(str), x.iloc[3:]
        dates = pd.to_datetime(body.iloc[:, 0], errors="coerce")
        for col, name in names.items():
            m = BULLETIN_COLUMN.match(name)
            if m:
                frames.append(pd.DataFrame({
                    "date": dates, "geo": m["geo"], "product": m["product"], "tax": TAX[m["tax"]],
                    # quoted in euro per 1000 litres for every country
                    "price": pd.to_numeric(body[col], errors="coerce") / 1000,
                }))
    # dropna takes out the notes under the table; the rest is a guard, today there are
    # no zeros and no repeated weeks, but either would break the weekly series later
    out = pd.concat(frames, ignore_index=True).dropna()
    out = out[out.price > 0].drop_duplicates(["date", "geo", "product", "tax"])
    return out.sort_values(["geo", "product", "tax", "date"]).reset_index(drop=True)

def oil_bulletin(refresh=False):
    # The page is only read for the link and isn't archived: its element ids are random, so
    # every copy would look new. If it's down, fall back to the last workbook we stored.
    try:
        link = bulletin_link(net.get(settings.oil_bulletin_page).text)
    except (httpx.HTTPError, RuntimeError) as exc:
        old = net.latest("oil_bulletin", "history", "xlsx")
        if old is None:
            raise
        net.events.append({"source": "oil_bulletin", "name": "page", "fallback": old.name, "error": str(exc)})
        return parse_bulletin(old.read_bytes())

    raw = net.fetch(link, None, source="oil_bulletin", name="history", ext="xlsx",
                    refresh=refresh, timeout=300)
    return parse_bulletin(raw)