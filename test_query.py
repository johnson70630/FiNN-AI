#!/usr/bin/env python3
"""
Test script for the integrated query endpoint
"""
import requests
import json
import sys

def test_query(question):
    """Test the query endpoint with a question"""
    url = "http://localhost:8000/query"
    headers = {"Content-Type": "application/json"}
    data = {"question": question}
    
    print(f"🔍 Sending query: {question}")
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n🔧 Using service: {result.get('service', 'unknown')}")
            print("\n🤖 Answer:\n")
            print(result["answer"])
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        test_query(question)
    else:
        print("Please provide a question as an argument")
        print("Example: python test_query.py What are the latest trends in cryptocurrency?")
