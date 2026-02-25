import streamlit as st
from dotenv import load_dotenv
import os
import requests
import datetime

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
        "Authorization": f"Bearer {monday_api_key}",
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

# Function to fetch items from a specific board
def get_board_items(board_id):
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": f"Bearer {monday_api_key}",
        "Content-Type": "application/json"
    }
    query = f"""
    query {{
        boards(ids: [{board_id}]) {{
            items_page {{
                items {{
                    id
                    name
                    column_values {{
                        id
                        text
                    }}
                }}
            }}
        }}
    }}
    """
    try:
        response = requests.post(url, json={'query': query}, headers=headers)
        response.raise_for_status()
        data = response.json()
        if 'errors' in data:
            st.error(f"GraphQL Errors: {data['errors']}")
            return []
        return data.get('data', {}).get('boards', [{}])[0].get('items_page', {}).get('items', [])

def clean_data(raw_items):
    cleaned = []
    data_quality_report = {
        'missing_deal_values': 0,
        'missing_probability': 0,
        'rows_excluded_invalid_dates': 0,
        'rows_excluded_invalid_numeric': 0
    }
    
    for item in raw_items:
        cleaned_item = {
            'id': item['id'],
            'name': item['name'].lower().strip() if item['name'] else '',
            'deal_value': None,
            'probability': None,
            'date': None
        }
        
        for col in item['column_values']:
            text = col['text'].strip() if col['text'] else ''
            if not text:
                continue
            
            # Map probability
            if text.lower() == 'high':
                cleaned_item['probability'] = 0.8
            elif text.lower() == 'medium':
                cleaned_item['probability'] = 0.5
            elif text.lower() == 'low':
                cleaned_item['probability'] = 0.2
            
            # Parse deal value
            try:
                cleaned_item['deal_value'] = float(text.replace(',', '').replace('$', ''))
            except ValueError:
                pass
            
            # Parse date (assume YYYY-MM-DD format)
            try:
                cleaned_item['date'] = datetime.datetime.strptime(text, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Check for exclusions
        if cleaned_item['deal_value'] is None:
            data_quality_report['rows_excluded_invalid_numeric'] += 1
            continue  # Exclude row
        
        if cleaned_item['date'] is None:
            data_quality_report['rows_excluded_invalid_dates'] += 1
            # Note: spec says exclude if time filtering required, but for now exclude
        
        # Count missing in included rows
        if cleaned_item['probability'] is None:
            data_quality_report['missing_probability'] += 1
        
        cleaned.append(cleaned_item)
    
    # Since we excluded invalid deal_value, missing_deal_values is 0 for included
    data_quality_report['missing_deal_values'] = data_quality_report['rows_excluded_invalid_numeric']
    
    return cleaned, data_quality_report
    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {str(e)}")
        return []

# Streamlit UI
st.title("Monday.com Business Intelligence Agent")
st.subheader("Phase 1: Fetching Board Names")

boards = get_boards()

if boards:
    st.write("### Boards Found:")
    for board in boards:
        st.write(f"- **ID:** {board['id']}, **Name:** {board['name']}")
else:
    st.write("No boards found. Please check your API key and connection.")

st.subheader("Phase 2: Fetching Board Items")

# Hardcoded board IDs based on fetched boards
deals_board_id = "5026839585"  # Deals board
work_orders_board_id = "5026840149"  # Work_Order_Tracker_Data board

st.write("### Deals Board Items:")
deals_items = get_board_items(deals_board_id)
st.json(deals_items)

st.write("### Work Orders Board Items:")
work_orders_items = get_board_items(work_orders_board_id)
st.json(work_orders_items)

st.subheader("Phase 3: Data Cleaning")

st.write("### Cleaned Deals Data:")
cleaned_deals, report_deals = clean_data(deals_items)
st.json(cleaned_deals)
st.write("### Data Quality Report for Deals:")
st.json(report_deals)

st.write("### Cleaned Work Orders Data:")
cleaned_work_orders, report_work_orders = clean_data(work_orders_items)
st.json(cleaned_work_orders)
st.write("### Data Quality Report for Work Orders:")
st.json(report_work_orders)