import os
import requests
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
IP_QUALITY_SCORE_API_KEY = os.getenv("IP_QUALITY_SCORE_API_KEY")
if not IP_QUALITY_SCORE_API_KEY:
    print("WARNING: IP_QUALITY_SCORE_API_KEY not found in environment variables. Service will not function correctly for IP checks.")
    # raise ValueError("IP_QUALITY_SCORE_API_KEY is required. Please set it in your .env file or environment.")

IPQS_API_URL_TEMPLATE = "https://www.ipqualityscore.com/api/json/ip/{api_key}/{ip_address}"

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Lead Verification Service",
    description="API to verify the authenticity of incoming leads based on co-registration filtering rules.",
    version="1.0.0"
)

# --- Pydantic Models for Request & Response ---
class LeadDataInput(BaseModel):
    # Example lead fields - customize these to match your actual lead structure
    # first_name: Optional[str] = None
    # last_name: Optional[str] = None
    # email: Optional[EmailStr] = None
    # phone: Optional[str] = None
    # This is the state the user *claims* to be from in the form
    submitted_state: str = Field(..., description="The U.S. state submitted by the user in the form (e.g., 'California' or 'CA').")
    
    # Data injected by the frontend lead-filter.js script
    time_on_page: int = Field(..., description="Time spent on the page in seconds before form submission.")
    user_agent: str = Field(..., description="Browser's user agent string.")
    # The IP address should be extracted from the request headers by FastAPI
    # but for purposes of testing we will pass it in the request as a parameter
    # ip_address: str = Field(..., description="user's ip address")


class LeadVerificationResponse(BaseModel):
    is_genuine: bool
    reason: Optional[str] = None
    details: Optional[dict] = None

# --- State Abbreviation to Full Name Mapping (Simple Example) ---
# For a robust solution, use a comprehensive library or a more complete mapping.
US_STATE_MAP = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    # Include DC and territories if needed
    "DC": "District of Columbia"
}
# Create a reverse map for convenience (Full Name -> Abbreviation) and normalize keys
US_STATE_MAP_REVERSE = {v.lower(): k for k, v in US_STATE_MAP.items()}
US_STATE_FULL_NAMES_LOWER = {name.lower() for name in US_STATE_MAP.values()}
US_STATE_ABBREVIATIONS_LOWER = {abbr.lower() for abbr in US_STATE_MAP.keys()}

def normalize_state(submitted_state: str) -> Optional[str]:
    """Normalizes a submitted state (name or abbreviation) to its full name, lowercase."""
    s_lower = submitted_state.strip().lower()
    if s_lower in US_STATE_FULL_NAMES_LOWER:
        return s_lower
    if s_lower in US_STATE_ABBREVIATIONS_LOWER:
        # Convert abbreviation to full name, then lowercase
        full_name = US_STATE_MAP.get(s_lower.upper())
        return full_name.lower() if full_name else None
    return None


# --- API Endpoint ---
@app.post("/isGenuineLead/", response_model=LeadVerificationResponse)
async def is_genuine_lead(lead_data: LeadDataInput, request: Request):
    """
    Validates a lead based on time on page, IP geolocation, and proxy/VPN detection.
    """
    client_ip = request.client.host
    # client_ip = lead_data.ip_address

    print("Client ip: " + client_ip)
    print("Time on page: " + str(lead_data.time_on_page))

    if not client_ip:
        # Should not happen with FastAPI if properly configured behind a proxy
        return LeadVerificationResponse(is_genuine=False, reason="Could not determine client IP address.")

    # 1. Time on page check (must be greater than 2 seconds)
    if lead_data.time_on_page <= 2:
        return LeadVerificationResponse(
            is_genuine=False,
            reason="Low time on page.",
            details={"time_on_page": lead_data.time_on_page, "requirement": "> 2 seconds"}
        )

    # If API key is not set, we can't perform IP checks.
    # Depending on policy, you might want to fail open (less secure) or closed (more secure).
    # Here, we'll fail closed for IP-dependent checks if the key is missing.
    if not IP_QUALITY_SCORE_API_KEY or IP_QUALITY_SCORE_API_KEY == "YOUR_IPQUALITYSCORE_API_KEY":
        print(f"WARNING: IPQualityScore API key not configured. Skipping IP checks for IP: {client_ip}.")
        # If we skip IP checks, we might consider the lead genuine based on other factors,
        # or fail it if IP checks are mandatory. For this example, let's assume IP checks are
        # critical. If you want to allow leads without IP checks, modify this logic.
        return LeadVerificationResponse(
            is_genuine=False, # Or True, depending on your risk tolerance without IP checks
            reason="IP validation service not configured (API key missing). Cannot verify IP-related criteria.",
            details={"client_ip": client_ip}
        )

    # 2. & 3. IPQualityScore API for Proxy/VPN and Geolocation
    ipqs_url = IPQS_API_URL_TEMPLATE.format(api_key=IP_QUALITY_SCORE_API_KEY, ip_address=client_ip)
    params = {
        "user_agent": lead_data.user_agent,
        "strictness": 1,  # 0-3, higher is more aggressive. 1 is a good balance.
        "allow_public_access_points": "true", # Consider blocking known public Wi-Fi, etc.
        # "mobile": "true" # if you want to get mobile carrier info, etc.
    }

    ipqs_data = None
    try:
        # Using httpx for async requests would be better in a high-traffic FastAPI app
        # For simplicity, using synchronous requests here.
        response = requests.get(ipqs_url, params=params, timeout=10) # Increased timeout
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        ipqs_data = response.json()

        print("--- Full IPQS Response ---")
        import json
        print(json.dumps(ipqs_data, indent=4))
        print("--------------------------")

        if not ipqs_data.get("success", False):
            error_message = ipqs_data.get("message", "Unknown error from IPQualityScore")
            print(f"IPQualityScore API error for IP {client_ip}: {error_message}")
            return LeadVerificationResponse(
                is_genuine=False,
                reason=f"IP validation failed: {error_message}",
                details={"client_ip": client_ip, "ipqs_response": ipqs_data}
            )

    except requests.exceptions.Timeout:
        print(f"IPQualityScore API timeout for IP {client_ip}.")
        # Decide how to handle timeouts: fail open (less secure) or fail closed (more secure)
        return LeadVerificationResponse(is_genuine=False, reason="IP validation service timed out.", details={"client_ip": client_ip})
    except requests.exceptions.RequestException as e:
        print(f"Error calling IPQualityScore API for IP {client_ip}: {e}")
        return LeadVerificationResponse(is_genuine=False, reason="IP validation service request exception.", details={"client_ip": client_ip, "error": str(e)})


    # 2. No proxy/VPN is detected
    # IPQS fields: proxy, vpn, tor
    if ipqs_data.get("proxy") or ipqs_data.get("vpn") or ipqs_data.get("tor"):
        detection_type = []
        if ipqs_data.get("proxy"): detection_type.append("proxy")
        if ipqs_data.get("vpn"): detection_type.append("vpn")
        if ipqs_data.get("tor"): detection_type.append("tor")
        return LeadVerificationResponse(
            is_genuine=False,
            reason=f"{', '.join(detection_type).capitalize()} detected.",
            details={
                "client_ip": client_ip,
                "proxy": ipqs_data.get("proxy"),
                "vpn": ipqs_data.get("vpn"),
                "tor": ipqs_data.get("tor"),
                "fraud_score": ipqs_data.get("fraud_score")
            }
        )

    # 3. The IP address geolocation must match the U.S. state from which the request is being submitted
    ip_country_code = ipqs_data.get("country_code")
    ip_state_name = ipqs_data.get("region") # IPQualityScore uses "region" for state name

    if ip_country_code != "US":
        return LeadVerificationResponse(
            is_genuine=False,
            reason="IP address is not from the U.S.",
            details={
                "client_ip": client_ip,
                "ip_country": ip_country_code,
                "ip_state": ip_state_name,
                "submitted_state": lead_data.submitted_state
            }
        )

    normalized_submitted_state = normalize_state(lead_data.submitted_state)
    normalized_ip_state = normalize_state(ip_state_name) if ip_state_name else None

    if not normalized_submitted_state:
        return LeadVerificationResponse(
            is_genuine=False,
            reason="Submitted state is not a valid U.S. state name or abbreviation.",
            details={
                "client_ip": client_ip,
                "submitted_state_raw": lead_data.submitted_state,
                "ip_state_raw": ip_state_name
            }
        )
    
    if not normalized_ip_state or normalized_ip_state != normalized_submitted_state:
        return LeadVerificationResponse(
            is_genuine=False,
            reason="IP address geolocation (state) does not match submitted U.S. state.",
            details={
                "client_ip": client_ip,
                "ip_state_normalized": normalized_ip_state,
                "submitted_state_normalized": normalized_submitted_state,
                "ip_state_raw": ip_state_name,
                "submitted_state_raw": lead_data.submitted_state
            }
        )

    # All checks passed
    return LeadVerificationResponse(
        is_genuine=True,
        reason="Lead passed all verification checks.",
        details={
            "client_ip": client_ip,
            "time_on_page": lead_data.time_on_page,
            "ip_state": ip_state_name,
            "submitted_state": lead_data.submitted_state,
            "fraud_score": ipqs_data.get("fraud_score")
        }
    )

# To run the server (save this file as main.py):
# Ensure you have a .env file with your IP_QUALITY_SCORE_API_KEY
# Then run in your terminal:
# uvicorn main:app --reload
#
# Example POST request to test:
# curl -X POST "http://127.0.0.1:8000/isGenuineLead/" \
# -H "Content-Type: application/json" \
# -d '{
# "ip_address": "192.168.1.154",
# "submitted_state": "NY",
# "time_on_page": 10,
# "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
# }'

# curl -X POST "http://127.0.0.1:8000/isGenuineLead/" \
# -H "Content-Type: application/json" \
# -H "X-Forwarded-For: 173.56.213.26" \
# -d '{
#     "submitted_state": "New York",
#     "time_on_page": 15,
#     "user_agent": "curl/7.81.0"
# }'