#!/usr/bin/env python3
"""
Quick demo of the Sales Contact Finder Agent
"""

from sales_contact_finder import SalesContactFinderAgent

def main():
    print("🤖 Sales Contact Finder Agent - Quick Demo")
    print("=" * 50)
    
    # Your ContactOut API key
    API_KEY = "vBLwB5ZZVUM16VTeJvYxBhCC"
    
    # Initialize the agent
    agent = SalesContactFinderAgent(API_KEY)
    
    # Demo companies
    demo_companies = ["Apple", "Microsoft", "Google", "Amazon", "Tesla"]
    
    print(f"Testing with demo companies: {', '.join(demo_companies)}")
    print("-" * 50)
    
    for company in demo_companies:
        print(f"\n🔍 Finding sales contacts for: {company}")
        
        try:
            contacts = agent.find_sales_contacts(company)
            
            if contacts:
                print(f"✅ Found {len(contacts)} contacts:")
                for i, contact in enumerate(contacts, 1):
                    print(f"  {i}. {contact.name} ({contact.job_title})")
                    print(f"     📧 {contact.email}")
            else:
                print("❌ No contacts found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("-" * 30)

if __name__ == "__main__":
    main()