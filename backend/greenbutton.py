"""Green Button XML parser (ESPI IntervalBlock)."""
from datetime import datetime, timezone
from typing import List, Dict, Any
from lxml import etree


ESPI_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "espi": "http://naesb.org/espi",
}


def parse_green_button(xml_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse a Green Button ESPI XML file and return interval readings.

    Returns list of dicts: {ts_start, ts_end, kwh}
    """
    try:
        tree = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Invalid XML: {e}") from e

    # Find any IntervalBlock in any namespace
    interval_blocks = tree.xpath("//*[local-name()='IntervalBlock']")
    readings: List[Dict[str, Any]] = []

    # Try to find power-of-ten multiplier from ReadingType (default 0 => Wh, i.e. multiplier 1)
    # If units are watt-hours, we divide by 1000 to get kWh.
    # Green Button values are typically in Wh with powerOfTenMultiplier=0.
    multipliers = tree.xpath("//*[local-name()='powerOfTenMultiplier']/text()")
    pot = 0
    if multipliers:
        try:
            pot = int(multipliers[0])
        except ValueError:
            pot = 0
    # UOM 72 = Wh
    factor = (10 ** pot) / 1000.0  # convert to kWh assuming base unit is Wh

    for block in interval_blocks:
        readings_el = block.xpath(".//*[local-name()='IntervalReading']")
        for r in readings_el:
            start_el = r.xpath(".//*[local-name()='start']/text()")
            duration_el = r.xpath(".//*[local-name()='duration']/text()")
            value_el = r.xpath("./*[local-name()='value']/text()")
            if not start_el or not duration_el or not value_el:
                continue
            try:
                start_ts = int(start_el[0])
                duration = int(duration_el[0])
                raw_value = float(value_el[0])
            except ValueError:
                continue
            ts_start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            ts_end = datetime.fromtimestamp(start_ts + duration, tz=timezone.utc)
            kwh = raw_value * factor
            readings.append({
                "ts_start": ts_start,
                "ts_end": ts_end,
                "kwh": kwh,
            })

    readings.sort(key=lambda x: x["ts_start"])
    return readings


def generate_sample_xml(start: datetime, days: int = 3, interval_min: int = 15) -> bytes:
    """Generate a small sample Green Button XML for testing."""
    import random
    random.seed(42)
    seconds = interval_min * 60
    total = int((days * 86400) / seconds)
    entries = []
    ts = int(start.replace(tzinfo=timezone.utc).timestamp())
    for i in range(total):
        # base 200Wh + hvac-ish daily curve
        hour = ((ts + i * seconds) % 86400) / 3600.0
        cooling = max(0.0, 800 * (1 - abs(hour - 15) / 8.0))
        base = 200 + random.uniform(-40, 40)
        wh = base + cooling + random.uniform(0, 200)
        entries.append(
            f'<IntervalReading><timePeriod>'
            f'<duration>{seconds}</duration>'
            f'<start>{ts + i * seconds}</start>'
            f'</timePeriod><value>{int(wh)}</value></IntervalReading>'
        )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:espi="http://naesb.org/espi">
  <entry>
    <content type="application/xml">
      <ReadingType xmlns="http://naesb.org/espi">
        <powerOfTenMultiplier>0</powerOfTenMultiplier>
        <uom>72</uom>
      </ReadingType>
    </content>
  </entry>
  <entry>
    <content type="application/xml">
      <IntervalBlock xmlns="http://naesb.org/espi">
        {''.join(entries)}
      </IntervalBlock>
    </content>
  </entry>
</feed>
"""
    return xml.encode("utf-8")
