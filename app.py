import streamlit as st
from dotenv import load_dotenv
import os
import requests

# Load environment variables
load_dotenv(os.path.join(os.getcwd(), '.env'))

# Get API keys
monday_api_key = os.getenv('MONDAY_API_KEY')
openai_api_key = os.getenv('OPENAI_API_KEY')

# Check if MONDAY_API_KEY is available
if not monday_api_key:
    st.error("MONDAY_API_KEY not found in environment variables. Please set it in your .env file.")
    st.stop()

# Function to fetch boards from monday.com
def get_boards():
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": monday_api_key,
        "Content-Type": "application/json"
    }
    query = """
    query {
        boards {
            id
            name
        }
    }
    """
    try:
        response = requests.post(url, json={'query': query}, headers=headers)
        response.raise_for_status()  # Raise error for bad status codes
        data = response.json()
        if 'errors' in data:
            st.error(f"GraphQL Errors: {data['errors']}")
            return []
        return data.get('data', {}).get('boards', [])
    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {str(e)}")
        return []

# Streamlit UI
st.title("Monday.com Business Intelligence Agent - Phase 1")
st.subheader("Fetching Board Names")

boards = get_boards()

if boards:
    st.write("### Boards Found:")
    for board in boards:
        st.write(f"- **ID:** {board['id']}, **Name:** {board['name']}")
else:
    st.write("No boards found. Please check your API key and connection.")