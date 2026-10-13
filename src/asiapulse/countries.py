"""Country universe: 49 Asian economies, ISO3 codes and sub-regions."""
from __future__ import annotations

REGIONS: dict[str, list[tuple[str, str]]] = {
    "East Asia": [
        ("CHN", "China"), ("JPN", "Japan"), ("KOR", "South Korea"), ("MNG", "Mongolia"),
        ("PRK", "North Korea"), ("TWN", "Taiwan"),
    ],
    "Southeast Asia": [
        ("BRN", "Brunei"), ("KHM", "Cambodia"), ("IDN", "Indonesia"), ("LAO", "Laos"),
        ("MYS", "Malaysia"), ("MMR", "Myanmar"), ("PHL", "Philippines"), ("SGP", "Singapore"),
        ("THA", "Thailand"), ("TLS", "Timor-Leste"), ("VNM", "Vietnam"),
    ],
    "South Asia": [
        ("AFG", "Afghanistan"), ("BGD", "Bangladesh"), ("BTN", "Bhutan"), ("IND", "India"),
        ("MDV", "Maldives"), ("NPL", "Nepal"), ("PAK", "Pakistan"), ("LKA", "Sri Lanka"),
    ],
    "Central Asia": [
        ("KAZ", "Kazakhstan"), ("KGZ", "Kyrgyzstan"), ("TJK", "Tajikistan"),
        ("TKM", "Turkmenistan"), ("UZB", "Uzbekistan"),
    ],
    "West Asia": [
        ("ARM", "Armenia"), ("AZE", "Azerbaijan"), ("BHR", "Bahrain"), ("CYP", "Cyprus"),
        ("GEO", "Georgia"), ("IRN", "Iran"), ("IRQ", "Iraq"), ("ISR", "Israel"),
        ("JOR", "Jordan"), ("KWT", "Kuwait"), ("LBN", "Lebanon"), ("OMN", "Oman"),
        ("PSE", "Palestine"), ("QAT", "Qatar"), ("SAU", "Saudi Arabia"), ("SYR", "Syria"),
        ("TUR", "Turkey"), ("ARE", "UAE"), ("YEM", "Yemen"),
    ],
}

# Economies the World Bank WDI does not publish (or publishes almost nothing for).
NO_WDI_COVERAGE = {"TWN": "Not a World Bank member; WDI publishes no series.",
                   "PRK": "WDI publishes almost no macro series for DPRK."}

ISO_TO_NAME = {iso: name for rows in REGIONS.values() for iso, name in rows}
NAME_TO_ISO = {v: k for k, v in ISO_TO_NAME.items()}
ISO_TO_REGION = {iso: reg for reg, rows in REGIONS.items() for iso, _ in rows}
ALL_ISO = list(ISO_TO_NAME)
WDI_ISO = [i for i in ALL_ISO if i not in NO_WDI_COVERAGE]
