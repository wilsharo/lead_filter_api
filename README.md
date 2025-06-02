# To run the server (save this file as main.py):
# Ensure you have a .env file with your IP_QUALITY_SCORE_API_KEY
# Then run in your terminal:
# uvicorn main:app --reload
#
# Example POST request to test:

curl -X POST "http://127.0.0.1:8000/isGenuineLead/" \
-H "Content-Type: application/json" \
-d '{
"ip_address": "192.168.1.154",
"submitted_state": "NY",
"time_on_page": 10,
"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}'

curl -X POST "http://127.0.0.1:8000/isGenuineLead/" \
-H "Content-Type: application/json" \
-H "X-Forwarded-For: 173.56.213.26" \
-d '{
    "submitted_state": "New York",
    "time_on_page": 15,
    "user_agent": "curl/7.81.0"
}'