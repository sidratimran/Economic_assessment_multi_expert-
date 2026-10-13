"""Variable registry.

Every variable the platform uses is declared here once: where it comes from,
its unit, which policy pillar it belongs to, and whether higher is better.
The pipeline, risk model, policy engine and UI all read from this registry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicator:
    key: str
    code: str            # World Bank API code
    label: str
    unit: str
    pillar: str          # growth | labour | macro | external | fiscal | social | structure | governance | climate | context
    direction: int       # +1 higher is better, -1 higher is worse, 0 neutral/context
    source: int | str = 2  # World Bank API source id (2 = WDI, 3 = WGI) or "imf" for IMF WEO via DBnomics
    note: str = ""


INDICATORS: list[Indicator] = [
    # --- Growth & output
    Indicator("gdp_usd", "NY.GDP.MKTP.CD", "GDP (current US$)", "US$", "context", 0),
    Indicator("gdp_real", "NY.GDP.MKTP.KD", "GDP (constant 2015 US$)", "US$", "growth", 0),
    Indicator("gdp_growth", "NY.GDP.MKTP.KD.ZG", "Real GDP growth", "%", "growth", +1),
    Indicator("gdp_pc_ppp", "NY.GDP.PCAP.PP.KD", "GDP per capita, PPP (constant 2021 int$)", "int$", "growth", +1),
    # --- Labour market
    Indicator("emp_ratio", "SL.EMP.TOTL.SP.ZS", "Employment-to-population ratio, 15+ (ILO modelled)", "%", "labour", +1),
    Indicator("unemp", "SL.UEM.TOTL.ZS", "Unemployment rate (ILO modelled)", "%", "labour", -1),
    Indicator("youth_unemp", "SL.UEM.1524.ZS", "Youth unemployment, 15-24 (ILO modelled)", "%", "labour", -1),
    Indicator("female_lfp", "SL.TLF.CACT.FE.ZS", "Female labour-force participation, 15+", "%", "labour", +1),
    Indicator("vuln_emp", "SL.EMP.VULN.ZS", "Vulnerable employment (% of total)", "%", "labour", -1),
    Indicator("agri_emp", "SL.AGR.EMPL.ZS", "Employment in agriculture (% of total)", "%", "structure", 0),
    # --- Macro stability
    Indicator("inflation", "FP.CPI.TOTL.ZG", "Consumer-price inflation", "%", "macro", -1),
    Indicator("reserves_months", "FI.RES.TOTL.MO", "Reserves in months of imports", "months", "macro", +1),
    # --- External position
    Indicator("current_account", "BN.CAB.XOKA.GD.ZS", "Current-account balance (% GDP)", "% GDP", "external", +1),
    Indicator("fdi", "BX.KLT.DINV.WD.GD.ZS", "FDI net inflows (% GDP)", "% GDP", "external", +1),
    Indicator("exports", "NE.EXP.GNFS.ZS", "Exports of goods & services (% GDP)", "% GDP", "external", 0),
    Indicator("ext_debt", "DT.DOD.DECT.GN.ZS", "External debt stock (% GNI)", "% GNI", "external", -1),
    Indicator("remittances", "BX.TRF.PWKR.DT.GD.ZS", "Personal remittances received (% GDP)", "% GDP", "external", 0),
    Indicator("oil_rents", "NY.GDP.PETR.RT.ZS", "Oil rents (% GDP)", "% GDP", "external", 0),
    Indicator("resource_rents", "NY.GDP.TOTL.RT.ZS", "Total natural-resource rents (% GDP)", "% GDP", "external", 0),
    # --- Fiscal
    Indicator("gov_debt", "GC.DOD.TOTL.GD.ZS", "Public debt (% GDP; IMF WEO gross debt, WDI fallback)", "% GDP", "fiscal", -1,
              note="IMF WEO general-government gross debt preferred; WDI central-government debt fills gaps."),
    Indicator("primary_balance", "GGXONLB_NGDP", "Primary fiscal balance (% GDP)", "% GDP", "fiscal", +1, source="imf"),
    Indicator("fiscal_balance", "GGXCNL_NGDP", "Overall fiscal balance (% GDP)", "% GDP", "fiscal", +1, source="imf"),
    Indicator("tax_rev", "GC.TAX.TOTL.GD.ZS", "Tax revenue (% GDP)", "% GDP", "fiscal", +1),
    Indicator("health_exp", "SH.XPD.GHED.GD.ZS", "Government health spending (% GDP)", "% GDP", "fiscal", +1),
    Indicator("edu_exp", "SE.XPD.TOTL.GD.ZS", "Government education spending (% GDP)", "% GDP", "fiscal", +1),
    # --- Social
    Indicator("poverty", "SI.POV.DDAY", "Extreme poverty headcount (international line)", "% pop", "social", -1),
    Indicator("gini", "SI.POV.GINI", "Gini index", "index", "social", -1),
    Indicator("neet_youth", "SL.UEM.NEET.ZS", "Youth not in education, employment or training", "%", "social", -1),
    # --- Demography & context
    Indicator("population", "SP.POP.TOTL", "Population", "people", "context", 0),
    Indicator("pop_growth", "SP.POP.GROW", "Population growth", "%", "context", 0),
    Indicator("dependency", "SP.POP.DPND", "Age-dependency ratio", "% working-age", "context", 0),
    Indicator("urban", "SP.URB.TOTL.IN.ZS", "Urban population", "% pop", "context", 0),
    # --- Structure & capability
    Indicator("manufacturing", "NV.IND.MANF.ZS", "Manufacturing value added (% GDP)", "% GDP", "structure", +1),
    Indicator("agriculture", "NV.AGR.TOTL.ZS", "Agriculture value added (% GDP)", "% GDP", "structure", 0),
    Indicator("services", "NV.SRV.TOTL.ZS", "Services value added (% GDP)", "% GDP", "structure", 0),
    Indicator("trade_open", "NE.TRD.GNFS.ZS", "Trade openness (exports + imports, % GDP)", "% GDP", "structure", 0),
    # --- Technology & innovation
    Indicator("internet", "IT.NET.USER.ZS", "Internet users (% pop)", "% pop", "technology", +1),
    Indicator("broadband", "IT.NET.BBND.P2", "Fixed broadband subscriptions (per 100 people)", "per 100", "technology", +1),
    Indicator("mobile", "IT.CEL.SETS.P2", "Mobile subscriptions (per 100 people)", "per 100", "technology", +1),
    Indicator("hightech_exports", "TX.VAL.TECH.MF.ZS", "High-technology exports (% of manufactured exports)", "%", "technology", +1),
    Indicator("ict_services_exports", "BX.GSR.CCIS.ZS", "ICT service exports (% of service exports)", "%", "technology", +1),
    Indicator("rnd", "GB.XPD.RSDV.GD.ZS", "R&D expenditure (% GDP)", "% GDP", "technology", +1),
    Indicator("patents_resident", "IP.PAT.RESD", "Patent applications by residents", "count", "context", 0,
              note="Converted to patents per million people for scoring."),
    Indicator("researchers", "SP.POP.SCIE.RD.P6", "Researchers in R&D (per million people)", "per million", "technology", +1),
    # --- Human capital & health
    Indicator("tertiary_enrol", "SE.TER.ENRR", "Tertiary school enrolment (% gross)", "%", "human_capital", +1),
    Indicator("secondary_enrol", "SE.SEC.ENRR", "Secondary school enrolment (% gross)", "%", "human_capital", +1),
    Indicator("life_exp", "SP.DYN.LE00.IN", "Life expectancy at birth", "years", "human_capital", +1),
    Indicator("u5_mortality", "SH.DYN.MORT", "Under-5 mortality (per 1,000 live births)", "per 1,000", "human_capital", -1),
    Indicator("undernourishment", "SN.ITK.DEFC.ZS", "Prevalence of undernourishment", "% pop", "social", -1),
    # --- Infrastructure & energy access
    Indicator("electricity", "EG.ELC.ACCS.ZS", "Access to electricity", "% pop", "infrastructure", +1),
    Indicator("clean_cooking", "EG.CFT.ACCS.ZS", "Access to clean cooking fuels", "% pop", "infrastructure", +1),
    Indicator("logistics", "LP.LPI.OVRL.XQ", "Logistics Performance Index (1-5)", "score", "infrastructure", +1),
    Indicator("water", "SH.H2O.BASW.ZS", "Basic drinking-water access", "% pop", "infrastructure", +1),
    # --- Financial development
    Indicator("private_credit", "FS.AST.PRVT.GD.ZS", "Domestic credit to private sector (% GDP)", "% GDP", "finance", +1),
    Indicator("account_ownership", "FX.OWN.TOTL.ZS", "Account ownership, 15+ (Global Findex)", "%", "finance", +1),
    Indicator("npl", "FB.AST.NPER.ZS", "Bank non-performing loans (% gross loans)", "%", "finance", -1),
    # --- Climate & environment
    Indicator("renewables", "EG.FEC.RNEW.ZS", "Renewable share of final energy", "%", "climate", +1),
    Indicator("co2_pc", "EN.GHG.CO2.PC.CE.AR5", "CO2 emissions per capita (excl. LULUCF)", "t CO2e", "climate", -1),
    Indicator("pm25", "EN.ATM.PM25.MC.M3", "PM2.5 air pollution, mean annual exposure", "µg/m³", "climate", -1),
    # --- Governance (WGI, estimate scale ≈ -2.5 … +2.5)
    Indicator("gov_effectiveness", "GOV_WGI_GE.EST", "Government effectiveness (WGI)", "score", "governance", +1, source=3),
    Indicator("political_stability", "GOV_WGI_PV.EST", "Political stability & absence of violence (WGI)", "score", "governance", +1, source=3),
    Indicator("rule_of_law", "GOV_WGI_RL.EST", "Rule of law (WGI)", "score", "governance", +1, source=3),
    Indicator("control_corruption", "GOV_WGI_CC.EST", "Control of corruption (WGI)", "score", "governance", +1, source=3),
]

BY_KEY = {i.key: i for i in INDICATORS}
WB_INDICATORS = [i for i in INDICATORS if i.source in (2, 3)]

PILLAR_LABELS = {
    "growth": "Growth momentum",
    "labour": "Labour market",
    "macro": "Macro stability",
    "external": "External resilience",
    "fiscal": "Fiscal space",
    "social": "Social inclusion",
    "structure": "Structural transformation",
    "governance": "Institutions",
    "climate": "Climate & environment",
    "technology": "Technology & innovation",
    "human_capital": "Human capital & health",
    "infrastructure": "Infrastructure & access",
    "finance": "Financial development",
}


def label(key: str) -> str:
    return BY_KEY[key].label if key in BY_KEY else key
