# bills.py
# --------
# This file is your "menu" — the single place where you manage which bills to track.
# To add a new bill, copy one of the entries below and fill in the details.
# You never need to touch the other files just to add a new bill.
#
# HOW THE XML URL IS BUILT (so you understand why these fields exist):
#   https://ilga.gov/ftp/legislation/104/BillStatus/XML/10400HB5411.xml
#                                          ^^^                ^^^^^
#                                       ga_number          ga_prefix + bill_type + bill_number
#
# SESSION REFERENCE:
#   104th General Assembly (2025-2026) = current session


# --- Session definitions ---
# These hold the technical IDs the ILGA website uses internally.
# You won't need to change these unless a new legislative session starts.

SESSION_104 = {
    "ga_number": "104",     # Used in the XML file path
    "ga_prefix": "10400",   # Used in the XML filename itself
    "gaid": "18",           # Illinois General Assembly's internal session ID
    "session_id": "114",    # Used in bill status page URLs
}

SESSION_103 = {
    "ga_number": "103",
    "ga_prefix": "10300",
    "gaid": "17",
    "session_id": "112",
}


# --- Your bill list ---
# Each bill is a Python "dictionary" — a set of labeled values, like a form.
# The ** before SESSION_104 means "copy all fields from that dictionary into this one"
# so you don't have to repeat the session info for every bill.

BILLS = [

    # ---- NEW BILLS (104th GA, 2025-2026) ----

    {
        "friendly_name": "Rabies Vaccination",
        "bill_type": "HB",
        "bill_number": "5411",
        **SESSION_104,
    },
    {
        "friendly_name": "Animal Advocate",
        "bill_type": "HB",
        "bill_number": "4475",
        **SESSION_104,
    },
    {
        "friendly_name": "Public Access to View Stray Animals",
        "bill_type": "HB",
        "bill_number": "4748",
        **SESSION_104,
    },
    {
        "friendly_name": "Traveling Animal Acts",
        "bill_type": "HB",
        "bill_number": "4255",
        **SESSION_104,
    },
    {
        "friendly_name": "Animal Testing",
        "bill_type": "HB",
        "bill_number": "4400",
        **SESSION_104,
    },

    # IACA Disclosure — bill number TBD, placeholder until correct number confirmed
    # Uncomment and fill in the number when ready:
    # {
    #     "friendly_name": "IACA Disclosure",
    #     "bill_type": "SB",
    #     "bill_number": "????",
    #     **SESSION_104,
    # },

]


# --- District definitions ---
# Used in the app to flag bills from sponsors in your service area.
# Format: "Chamber District#" — must match how ILGA lists it on member pages.

OUR_DISTRICTS = [
    "52nd",   # Senate - Paul Faraci
    "103rd",  # House - Carol Ammons
]

NEIGHBOR_DISTRICTS = [
    "51st",   # Senate - Chapin Rose
    "88th",   # House
    "101st",  # House - Chris Miller
    "102nd",  # House
    "103rd",  # House (also ours)
    "104th",  # House
    "107th",  # House - fringe of service area
]


# ---------------------------------------------------------------------------
# CUSTOM BILLS — added through the Streamlit UI, saved to custom_bills.json
# ---------------------------------------------------------------------------
# This function is what the scraper calls. It returns the hardcoded list above
# PLUS any bills the user has added through the app's "Add Bill" form.
#
# Why a separate JSON file instead of editing bills.py directly?
#   - bills.py is code — it's easy to accidentally break with a typo
#   - custom_bills.json is data — safe to read/write programmatically
#   - keeps your "known good" baseline separate from user additions

import json
import os

CUSTOM_BILLS_PATH = os.path.join(os.path.dirname(__file__), "custom_bills.json")


def load_custom_bills():
    """Reads user-added bills from custom_bills.json. Returns empty list if file doesn't exist."""
    if not os.path.exists(CUSTOM_BILLS_PATH):
        return []
    try:
        with open(CUSTOM_BILLS_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_custom_bills(bills_list):
    """Writes the custom bills list to custom_bills.json."""
    with open(CUSTOM_BILLS_PATH, "w") as f:
        json.dump(bills_list, f, indent=2)


def get_all_bills():
    """Returns the full combined list: hardcoded bills + user-added bills."""
    return BILLS + load_custom_bills()


def remove_custom_bill(bill_id):
    """Removes a bill from the custom list by its bill_id (e.g. 'HB1234')."""
    custom = load_custom_bills()
    updated = [b for b in custom if f"{b['bill_type']}{b['bill_number']}" != bill_id]
    save_custom_bills(updated)
    return len(custom) - len(updated)  # returns how many were removed
