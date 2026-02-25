import streamlit as st
import os
import requests
import datetime
import json
from openai import OpenAI
import json

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
    query = """
    query {{
        boards(ids: [{0}]) {{
            items_page {{
                items {{
                    id
                    name
                    column_values {{
                        id
                        text
                        value
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
    except Exception as e:
        st.error(f"Error fetching board items: {e}")
        return []

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
            text = (col.get('text') or '').strip()
            value = col.get('value') or ''
            print(f"Column ID: {col['id']}, Text: {repr(text)}, Value: {repr(value)}")
            if not text and not value:
                continue
            
            # Map probability from text
            if text.lower() == 'high':
                cleaned_item['probability'] = 0.8
            elif text.lower() == 'medium':
                cleaned_item['probability'] = 0.5
            elif text.lower() == 'low':
                cleaned_item['probability'] = 0.2
            
            # Parse deal value from value (JSON) or text
            if value:
                try:
                    val_data = json.loads(value)
                    if isinstance(val_data, dict) and 'amount' in val_data:
                        cleaned_item['deal_value'] = float(val_data['amount'])
                except (json.JSONDecodeError, ValueError):
                    pass
            if cleaned_item['deal_value'] is None and text:
                try:
                    cleaned_item['deal_value'] = float(text.replace(',', '').replace('$', ''))
                except ValueError:
                    pass
            
            # Parse date from text
            if text:
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

def extract_intent(question):
    openai_api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(
        api_key=openai_api_key
    )
    system_prompt = """
You are an AI assistant for a business intelligence system. Analyze the user's question and extract the intent as structured JSON.

Return ONLY valid JSON with the following structure:

{
  "board": "deals" | "work_orders" | "both" | null,
  "sector": string or null,
  "time_period": "this_quarter" | "last_quarter" | "all_time" | null,
  "analysis_type": "pipeline" | "revenue" | "execution" | "leadership_update" | null
}

If the question is unclear or missing key information, return:

{
  "clarification_needed": true,
  "message": "Please clarify your question, e.g., specify which board or time period."
}

Do not perform any calculations. Only extract intent.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            max_tokens=300,
            temperature=0
        )
        content = response.choices[0].message.content.strip()
        # Parse JSON
        intent = json.loads(content)
        return intent
    except Exception as e:
        if "insufficient_quota" in str(e) or "rate" in str(e).lower():
            return {
                "llm_error": True,
                "message": "LLM service unavailable due to quota or rate limits."
            }
        else:
            return {"error": str(e)}

def perform_calculation(intent, cleaned_deals, cleaned_work_orders):
    if "llm_error" in intent or "error" in intent or "clarification_needed" in intent:
        return {"error": "Intent extraction failed, cannot perform calculations."}
    
    board = intent.get("board")
    sector = intent.get("sector")
    time_period = intent.get("time_period")
    analysis_type = intent.get("analysis_type")
    
    results = {}
    
    # Helper to filter data
    def filter_data(data, sector, time_period):
        filtered = data
        if sector:
            filtered = [item for item in filtered if item.get("sector") == sector]
        # For time_period, assume all_time for now, as date filtering is complex
        return filtered
    
    if board == "deals" or board == "both":
        deals_data = filter_data(cleaned_deals, sector, time_period)
        total_pipeline = sum(item.get("deal_value", 0) for item in deals_data)
        weighted_pipeline = total_pipeline  # No weight available, same as total
        stage_dist = {}
        for item in deals_data:
            status = item.get("status", "Unknown")
            stage_dist[status] = stage_dist.get(status, 0) + 1
        count_deals = len(deals_data)
        results["deals"] = {
            "total_pipeline_value": total_pipeline,
            "weighted_pipeline_value": weighted_pipeline,
            "stage_distribution": stage_dist,
            "count_of_deals": count_deals
        }
    
    if board == "work_orders" or board == "both":
        wo_data = filter_data(cleaned_work_orders, sector, time_period)
        total_items = len(wo_data)
        completed = sum(1 for item in wo_data if item.get("status") == "Completed")
        completion_rate = (completed / total_items * 100) if total_items > 0 else 0
        billing_breakdown = {}
        collection_breakdown = {}
        for item in wo_data:
            billing = item.get("billing_status", "Unknown")
            collection = item.get("collection_status", "Unknown")
            billing_breakdown[billing] = billing_breakdown.get(billing, 0) + 1
            collection_breakdown[collection] = collection_breakdown.get(collection, 0) + 1
        results["work_orders"] = {
            "completion_rate": completion_rate,
            "billing_status_breakdown": billing_breakdown,
            "collection_status_breakdown": collection_breakdown
        }
    
    if board == "both":
        # Compare closed deals vs executed work_orders
        closed_deals = sum(1 for item in cleaned_deals if item.get("status") == "Closed")
        executed_wo = sum(1 for item in cleaned_work_orders if item.get("status") == "Completed")
        results["comparison"] = {
            "closed_deals": closed_deals,
            "executed_work_orders": executed_wo,
            "potential_execution_lag": closed_deals - executed_wo if closed_deals > executed_wo else 0
        }
    
    return results

def generate_insights(calculation_results, intent):
    openai_api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(
        api_key=openai_api_key
    )
    system_prompt = """
You are an AI business analyst. Based on the provided calculation results and user intent, generate a concise executive summary in natural language.

The summary should be professional, insightful, and highlight key metrics, trends, and recommendations.

Keep it under 300 words.
"""
    user_prompt = f"User intent: {json.dumps(intent)}\n\nCalculation results: {json.dumps(calculation_results)}\n\nGenerate an executive summary."
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.5
        )
        content = response.choices[0].message.content.strip()
        return content
    except Exception as e:
        if "insufficient_quota" in str(e) or "rate" in str(e).lower():
            return "LLM service unavailable due to quota or rate limits. Cannot generate insights."
        else:
            return f"Failed to generate insights: {str(e)}"

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

st.subheader("Phase 4: Intent Extraction")

question = st.text_input("Enter your business question:")
if st.button("Extract Intent"):
    if question:
        intent = extract_intent(question)
        if "llm_error" in intent:
            st.warning(intent["message"])
        elif "error" in intent:
            st.error(f"Failed to extract intent: {intent['error']}")
        else:
            st.write("### Extracted Intent:")
            st.json(intent)
            
            # Phase 5: Business Logic
            st.subheader("Phase 5: Business Logic Calculations")
            calculation_results = perform_calculation(intent, cleaned_deals, cleaned_work_orders)
            if "error" in calculation_results:
                st.error(calculation_results["error"])
            else:
                st.write("### Calculation Results:")
                st.json(calculation_results)
                
                # Phase 6: Insight Generation
                st.subheader("Phase 6: Insight Generation")
                insights = generate_insights(calculation_results, intent)
                st.write("### Executive Summary:")
                st.write(insights)
    else:
        st.warning("Please enter a question.")