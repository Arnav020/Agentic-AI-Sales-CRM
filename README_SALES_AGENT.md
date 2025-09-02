# 🤖 Sales Contact Finder Agent

An AI-powered agent that finds sales person contact information using the ContactOut API. Simply provide a company name and get sales contacts with email addresses.

## 🔧 Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Key (SECURE METHOD)
```bash
# Set your ContactOut API key as an environment variable
export CONTACTOUT_API_KEY="your_actual_api_key_here"
```

### 3. Run the Agent
```bash
# Interactive mode
python3 sales_contact_finder.py

# Quick demo
python3 demo.py
```

## 🚀 Features

- **Smart Contact Search**: Finds sales-related contacts (Sales Directors, VPs, Managers, etc.)
- **Email Extraction**: Gets email addresses for found contacts  
- **JSON Export**: Save results to JSON files for later use
- **Fallback Data**: Generates realistic mock data when API is unavailable
- **Secure**: API keys handled through environment variables only

## 📋 Usage Examples

```python
from sales_contact_finder import SalesContactFinderAgent

# Initialize with your API key
agent = SalesContactFinderAgent(api_key)

# Find sales contacts for a company
contacts = agent.find_sales_contacts("Apple")

# Display results
agent.display_results(contacts)

# Save to JSON
agent.save_to_json(contacts, "apple_sales.json")
```

## 🛡️ Security Notes

- **Never commit API keys to git**
- Always use environment variables for sensitive data
- The `.env.example` file shows the correct format
- API keys are automatically excluded from git commits

## 📁 File Structure

- `sales_contact_finder.py` - Main agent code
- `demo.py` - Quick demonstration script  
- `requirements.txt` - Python dependencies
- `.env.example` - Environment variable template
- `README_SALES_AGENT.md` - This documentation

## 🎯 Demo Output

```
🔥 LIVE DEMO: SALES CONTACT FINDER AGENT
==================================================

🎯 TESTING WITH: NETFLIX
------------------------------
✅ Found 3 sales contact(s):
============================================================

1. John Smith
   📧 Email: john.smith@netflix.com
   💼 Title: Sales Director
   🏢 Company: Netflix
   🔗 LinkedIn: https://linkedin.com/in/john-smith-netflix
```

## 🤝 Contributing

This is part of the Agentic AI Sales CRM project. Follow security best practices when contributing.