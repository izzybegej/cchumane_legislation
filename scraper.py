# scraper.py
# ----------
# This is the "engine" of the project. It fetches and parses bill data.
#
# UPDATED APPROACH vs original version:
#
#   Districts: We now scrape the bill's HTML page to find the sponsor's
#   member profile link (e.g. /House/Members/Details/3288), then follow
#   that link to read the district number. This means it AUTOMATICALLY
#   stays correct after elections — we're always following whoever is
#   currently the sponsor, not looking up a hardcoded name.
#
#   Committee Schedules: ILGA's new site loads hearing schedules via
#   JavaScript, which scrapers can't read. Instead we build a direct link
#   to the chamber's schedule page so users can check with one click.
#
# FLOW FOR EACH BILL:
#   Stage 1 → Fetch XML           → status, sponsor, actions, synopsis
#   Stage 2 → Fetch bill HTML     → sponsor's member profile URL
#   Stage 3 → Fetch member page   → district number
#   Built   → Schedule URL, committee URL, full text URL (no fetch needed)


import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import time

from bills import get_all_bills, OUR_DISTRICTS, NEIGHBOR_DISTRICTS

BASE_URL = "https://www.ilga.gov"


# ---------------------------------------------------------------------------
# COMMITTEE URL LOOKUP
# ---------------------------------------------------------------------------
COMMITTEE_URLS = {
    # House
    "Rules Committee":                          "https://www.ilga.gov/house/committees/members/3066",
    "Agriculture & Conservation Committee":     "https://www.ilga.gov/house/committees/members/3067",
    "Judiciary - Criminal Committee":           "https://www.ilga.gov/house/committees/members/3076",
    "Environment & Energy Committee":           "https://www.ilga.gov/house/committees/members/3072",
    "Human Services Committee":                 "https://www.ilga.gov/house/committees/members/3074",
    # Senate
    "Assignments":                              "https://www.ilga.gov/senate/committees/members/3086",
    "Agriculture":                              "https://www.ilga.gov/senate/committees/members/3087",
    "Judiciary":                                "https://www.ilga.gov/senate/committees/members/3093",
    "Executive":                                "https://www.ilga.gov/senate/committees/members/3091",
}

# ---------------------------------------------------------------------------
# URL BUILDERS
# ---------------------------------------------------------------------------

def build_xml_url(bill):
    padded = bill["bill_number"].zfill(4)
    filename = f"{bill['ga_prefix']}{bill['bill_type']}{padded}.xml"
    return f"https://ilga.gov/ftp/legislation/{bill['ga_number']}/BillStatus/XML/{filename}"

def build_bill_page_url(bill):
    return (
        f"{BASE_URL}/Legislation/BillStatus"
        f"?DocNum={bill['bill_number']}"
        f"&GAID={bill['gaid']}"
        f"&DocTypeID={bill['bill_type']}"
        f"&SessionID={bill['session_id']}"
    )

def build_fulltext_url(bill):
    return (
        f"{BASE_URL}/Legislation/BillStatus/FullText"
        f"?DocNum={bill['bill_number']}"
        f"&GAID={bill['gaid']}"
        f"&DocTypeID={bill['bill_type']}"
        f"&SessionID={bill['session_id']}"
    )


# ---------------------------------------------------------------------------
# STAGE 1: Parse the XML
# ---------------------------------------------------------------------------

def parse_bill_xml(bill):
    url = build_xml_url(bill)
    print(f"  [Stage 1] Fetching XML...")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
        return None

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as e:
        print(f"  ERROR parsing XML: {e}")
        return None

    shortdesc = (root.findtext("shortdesc") or "").strip()
    synopsis  = (root.findtext("synopsis/SynopsisText") or "").strip()

    sponsors_raw  = (root.findtext("sponsor/sponsors") or "").strip()
    # ILGA sometimes uses " and " instead of a comma before the last sponsor.
    # We normalize " and " → ", " before splitting, so we always get individual names.
    sponsors_raw = re.sub(r'\s+and\s+', ', ', sponsors_raw)
    sponsors_list = [s.strip() for s in sponsors_raw.split(",") if s.strip()]
    primary_sponsor = sponsors_list[0] if sponsors_list else "Unknown"
    cosponsors      = sponsors_list[1:] if len(sponsors_list) > 1 else []

    last_date    = (root.findtext("lastaction/statusdate") or "").strip()
    last_chamber = (root.findtext("lastaction/chamber") or "").strip()
    last_action  = (root.findtext("lastaction/action") or "").strip()

    committee_name = extract_committee_from_action(last_action)
    action_history = parse_action_history(root)

    return {
        "shortdesc":       shortdesc,
        "synopsis":        synopsis,
        "primary_sponsor": primary_sponsor,
        "cosponsors":      cosponsors,
        "last_date":       last_date,
        "last_chamber":    last_chamber,
        "last_action":     last_action,
        "committee_name":  committee_name,
        "action_history":  action_history,
    }


# ---------------------------------------------------------------------------
# STAGE 2: Scrape the bill HTML page for the sponsor's member profile URL
# ---------------------------------------------------------------------------
# The HTML bill page contains:
#   Rep. <a href="/House/Members/Details/3288">Kelly M. Cassidy</a>
# We grab that href so we can follow it to get the district in Stage 3.
# This approach is election-proof — it always follows whoever is currently listed.

def get_sponsor_member_url(bill, sponsor_name):
    bill_url = build_bill_page_url(bill)
    print(f"  [Stage 2] Fetching bill HTML for sponsor link...")

    try:
        time.sleep(0.3)
        response = requests.get(bill_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  Could not fetch bill page: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    member_pattern = re.compile(r'/(house|senate)/members/details/\d+', re.IGNORECASE)

    # Try to match the sponsor's last name to a link
    last_name = sponsor_name.split()[-1].lower()
    for link in soup.find_all("a", href=member_pattern):
        if last_name in link.get_text().lower():
            href = link.get("href", "")
            clean = re.search(r'/(house|senate)/members/details/\d+', href, re.IGNORECASE)
            if clean:
                return BASE_URL + clean.group(0)

    # Fallback: return the first member link found
    first = soup.find("a", href=member_pattern)
    if first:
        href = first.get("href", "")
        clean = re.search(r'/(house|senate)/members/details/\d+', href, re.IGNORECASE)
        if clean:
            return BASE_URL + clean.group(0)

    return None


# ---------------------------------------------------------------------------
# STAGE 3: Fetch the member profile page and extract district
# ---------------------------------------------------------------------------
# Member pages show text like: "Representative · May 2011 - Present · 14th District"

def get_district_from_member_page(member_url):
    if not member_url:
        return "Unknown"

    print(f"  [Stage 3] Fetching member page for district...")

    try:
        time.sleep(0.3)
        response = requests.get(member_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  Could not fetch member page: {e}")
        return "Unknown"

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text()

    match = re.search(r'(\d+(?:st|nd|rd|th))\s+District', page_text, re.IGNORECASE)
    if match:
        return match.group(1)

    return "Unknown"


# ---------------------------------------------------------------------------
# SCHEDULE LINK BUILDER
# ---------------------------------------------------------------------------
# ILGA's hearing schedule is rendered via JavaScript on their redesigned site,
# which means scrapers cannot read the actual hearing data.
#
# Instead we return a direct URL to the appropriate chamber's schedule page.
# Users can open it with one click to see what's upcoming.
# For old session bills (103rd GA), this is left blank — that session is over.

SCHEDULE_URLS = {
    "House":  "https://www.ilga.gov/House/Schedules",
    "Senate": "https://www.ilga.gov/Senate/Schedules",
}

def get_schedule_url(chamber, ga_number):
    """Returns the schedule page URL for active bills, empty for old sessions."""
    if str(ga_number) != "104":
        return ""  # old session — no future hearings possible
    return SCHEDULE_URLS.get(chamber, "https://www.ilga.gov/House/Schedules")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def extract_committee_from_action(action_text):
    if not action_text:
        return ""
    for prefix in ["Referred to ", "Assigned to ", "Re-referred to "]:
        if prefix in action_text:
            return action_text.split(prefix, 1)[1].strip()
    return ""


def parse_action_history(root):
    """Groups the flat date/chamber/action siblings in the XML into triples."""
    actions_elem = root.find("actions")
    if actions_elem is None:
        return []
    children = list(actions_elem)
    history = []
    for i in range(0, len(children) - 2, 3):
        try:
            date    = (children[i].text   or "").strip()
            chamber = (children[i+1].text or "").strip()
            action  = (children[i+2].text or "").strip()
            if date and action:
                history.append(f"{date} [{chamber}] {action}")
        except IndexError:
            break
    return history


def get_district_flag(district):
    if not district or district == "Unknown":
        return ""
    num = re.sub(r'(st|nd|rd|th)$', '', district, flags=re.IGNORECASE)
    our_nums      = [re.sub(r'(st|nd|rd|th)$', '', d, flags=re.IGNORECASE) for d in OUR_DISTRICTS]
    neighbor_nums = [re.sub(r'(st|nd|rd|th)$', '', d, flags=re.IGNORECASE) for d in NEIGHBOR_DISTRICTS]
    if num in our_nums:
        return "⭐ Our District"
    elif num in neighbor_nums:
        return "📍 Neighbor District"
    return ""


def get_cosponsor_districts(cosponsors, bill):
    """
    Fetches the bill HTML once and extracts member URLs for all cosponsors,
    then fetches each member page to get their district.
    Returns list of "Name (District)" strings.
    """
    if not cosponsors:
        return []

    bill_url = build_bill_page_url(bill)
    try:
        time.sleep(0.3)
        response = requests.get(bill_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except requests.RequestException:
        return [f"{cs.replace('Rep. ','').replace('Sen. ','').strip()} (district unknown)"
                for cs in cosponsors]

    member_pattern = re.compile(r'/(house|senate)/members/details/\d+', re.IGNORECASE)

    # Build last_name → member URL mapping from all links on the page
    name_to_url = {}
    for link in soup.find_all("a", href=member_pattern):
        link_text = link.get_text().strip()
        if link_text:
            href = link.get("href", "")
            clean = re.search(r'/(house|senate)/members/details/\d+', href, re.IGNORECASE)
            if clean:
                name_to_url[link_text.split()[-1].lower()] = BASE_URL + clean.group(0)

    result = []
    for cosponsor in cosponsors:
        clean_name = cosponsor.replace("Rep. ", "").replace("Sen. ", "").strip()
        last_name  = clean_name.split()[-1].lower()
        member_url = name_to_url.get(last_name)
        if member_url:
            district = get_district_from_member_page(member_url)
            result.append(f"{clean_name} ({district})")
        else:
            result.append(f"{clean_name} (district unknown)")

    return result


# ---------------------------------------------------------------------------
# MAIN: Scrape a single bill (all stages)
# ---------------------------------------------------------------------------

def scrape_bill(bill):
    xml_data = parse_bill_xml(bill)
    if not xml_data:
        return None

    primary_sponsor = xml_data["primary_sponsor"]
    committee_name  = xml_data["committee_name"]
    chamber         = xml_data["last_chamber"]
    ga_number       = bill["ga_number"]

    # --- Sponsor district ---
    # For 104th GA bills: follow the member link from the bill HTML page.
    # For 103rd GA bills: the old session bill pages still exist, so we try the
    # same approach. If it fails (old pages sometimes have different HTML),
    # we fall back to "Session ended" since districts don't matter for old bills.
    member_url       = get_sponsor_member_url(bill, primary_sponsor)
    sponsor_district = get_district_from_member_page(member_url)

    # Friendly fallback for old session bills where district lookup failed
    if sponsor_district == "Unknown" and ga_number != "104":
        sponsor_district = "103rd GA"  # session ended, district less relevant

    district_flag = get_district_flag(sponsor_district)

    # --- Cosponsor districts ---
    # Only look up cosponsor districts for current session — old session
    # bills rarely have cosponsors we need to flag, and it saves web requests.
    if ga_number == "104" and xml_data["cosponsors"]:
        cosponsor_display = get_cosponsor_districts(xml_data["cosponsors"], bill)
    elif xml_data["cosponsors"]:
        # Old session: just list names without districts
        cosponsor_display = [
            cs.replace("Rep. ", "").replace("Sen. ", "").strip()
            for cs in xml_data["cosponsors"]
        ]
    else:
        cosponsor_display = []

    # --- Schedule link ---
    # ILGA's new site renders hearing schedules via JavaScript (can't scrape).
    # We provide a direct link to the schedule page instead.
    schedule_url = get_schedule_url(chamber, ga_number)

    committee_url = COMMITTEE_URLS.get(committee_name, "")
    clean_sponsor = primary_sponsor.replace("Rep. ", "").replace("Sen. ", "").strip()

    return {
        "friendly_name":    bill["friendly_name"],
        "bill_id":          f"{bill['bill_type']}{bill['bill_number']}",
        "session":          ga_number + "th GA",
        "title":            xml_data["shortdesc"],
        "primary_sponsor":  clean_sponsor,
        "sponsor_district": sponsor_district,
        "district_flag":    district_flag,
        "cosponsors":       " | ".join(cosponsor_display),
        "committee":        committee_name,
        "committee_url":    committee_url,
        "schedule_url":     schedule_url,      # renamed from upcoming_hearings
        "current_status":   xml_data["last_action"],
        "status_date":      xml_data["last_date"],
        "chamber":          chamber,
        "action_history":   " | ".join(xml_data["action_history"]),
        "synopsis":         xml_data["synopsis"],
        "bill_page_url":    build_bill_page_url(bill),
        "fulltext_url":     build_fulltext_url(bill),
    }


# ---------------------------------------------------------------------------
# MAIN: Scrape all bills
# ---------------------------------------------------------------------------

def scrape_all_bills():
    print("Starting bill scrape...")
    results = []
    all_bills = get_all_bills()  # hardcoded bills + any user-added bills
    for bill in all_bills:
        label = f"{bill['bill_type']}{bill['bill_number']} ({bill['friendly_name']})"
        print(f"\n--- Processing {label} ---")
        data = scrape_bill(bill)
        if data:
            results.append(data)
            print(f"  ✓ Complete")
        else:
            print(f"  ✗ Skipped (error)")
        time.sleep(0.5)
    print(f"\nScrape complete: {len(results)}/{len(all_bills)} bills succeeded.")
    return results


# ---------------------------------------------------------------------------
# FOR TESTING: Run `python scraper.py` directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = scrape_all_bills()
    print("\n--- RESULTS PREVIEW ---")
    for r in results:
        print(f"\n{r['bill_id']} | {r['friendly_name']}")
        print(f"  Sponsor:   {r['primary_sponsor']} ({r['sponsor_district']}) {r['district_flag']}")
        print(f"  Cosponsors: {r['cosponsors'] or 'none'}")
        print(f"  Committee: {r['committee']}")
        print(f"  Schedule:  {r['schedule_url'] or '(old session)'}")
        print(f"  Status:    {r['current_status']} ({r['status_date']})")
