#!/usr/bin/env python3
"""
Test script for advanced analysis reports

This script demonstrates how to generate and download the advanced analysis reports:
- Business Intelligence Report (multi-file)
- Profit Margin & Break-Even Analysis

Usage:
    python scripts/test_advanced_reports.py

Note: Requires admin authentication token
"""

import requests
import os
from datetime import datetime, timedelta

# Configuration
API_URL = os.environ.get('API_URL', 'http://localhost:5000/api')
TOKEN = os.environ.get('ADMIN_TOKEN', '')

if not TOKEN:
    print("ERROR: ADMIN_TOKEN environment variable not set")
    print("Please set it with: export ADMIN_TOKEN='your-jwt-token'")
    exit(1)

HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

OUTPUT_DIR = 'downloaded_reports'
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_business_intelligence_report():
    """Test Business Intelligence Report generation"""
    print("\n" + "="*60)
    print("Testing Business Intelligence Report")
    print("="*60)

    # Generate report for last year
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365)

    payload = {
        'start_date': str(start_date),
        'end_date': str(end_date)
    }

    print(f"\nGenerating report for date range: {start_date} to {end_date}")

    response = requests.post(
        f'{API_URL}/reports/generate/business-intelligence',
        json=payload,
        headers=HEADERS
    )

    if response.status_code != 200:
        print(f"ERROR: {response.status_code}")
        print(response.json())
        return None

    report_data = response.json()
    report_id = report_data['id']

    print(f"\nReport generated successfully!")
    print(f"Report ID: {report_id}")
    print(f"Status: {report_data['status']}")

    # Print metrics
    print("\nFinancial Metrics:")
    financial = report_data['metrics']['financial']
    print(f"  Total Revenue: ${financial['total_revenue']:,.2f}")
    print(f"  Total Profit: ${financial['total_profit']:,.2f}")
    print(f"  Overall Margin: {financial['overall_margin']:.1f}%")
    print(f"  YoY Growth: {financial['yoy_growth']:+.1f}%")

    print("\nOperational Metrics:")
    operational = report_data['metrics']['operational']
    print(f"  Total Customers: {operational['total_customers']:,}")
    print(f"  Total Orders: {operational['total_orders']:,}")
    print(f"  Avg Order Value: ${operational['avg_order_value']:,.2f}")
    print(f"  Revenue per Customer: ${operational['revenue_per_customer']:,.2f}")

    print(f"\nCategories Analyzed: {report_data['metrics']['categories_analyzed']}")
    print(f"Products Analyzed: {report_data['metrics']['products_analyzed']}")

    # Download all files
    print("\n" + "-"*60)
    print("Downloading report files...")
    print("-"*60)

    files_response = requests.get(
        f'{API_URL}/reports/{report_id}/files',
        headers=HEADERS
    )

    if files_response.status_code == 200:
        files_data = files_response.json()
        print(f"\nFound {files_data['total_files']} files to download:")

        for file_info in files_data['files']:
            filename = file_info['name']
            download_url = file_info['download_url']

            print(f"\n  Downloading: {filename} ({file_info['type']})")

            file_response = requests.get(
                f"{API_URL}{download_url}",
                headers=HEADERS
            )

            if file_response.status_code == 200:
                output_path = os.path.join(OUTPUT_DIR, filename)
                with open(output_path, 'wb') as f:
                    f.write(file_response.content)
                print(f"    Saved to: {output_path}")
            else:
                print(f"    ERROR: {file_response.status_code}")

    return report_id


def test_profit_margin_report():
    """Test Profit Margin & Break-Even Analysis"""
    print("\n" + "="*60)
    print("Testing Profit Margin & Break-Even Analysis Report")
    print("="*60)

    # Generate report for last year
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365)

    payload = {
        'start_date': str(start_date),
        'end_date': str(end_date)
    }

    print(f"\nGenerating report for date range: {start_date} to {end_date}")

    response = requests.post(
        f'{API_URL}/reports/generate/profit-margin',
        json=payload,
        headers=HEADERS
    )

    if response.status_code != 200:
        print(f"ERROR: {response.status_code}")
        print(response.json())
        return None

    report_data = response.json()
    report_id = report_data['id']

    print(f"\nReport generated successfully!")
    print(f"Report ID: {report_id}")
    print(f"Status: {report_data['status']}")

    # Print metrics
    print("\nOverall Performance:")
    overall = report_data['metrics']['overall_performance']
    print(f"  Total Revenue: ${overall['total_revenue']:,.2f}")
    print(f"  Total Cost: ${overall['total_cost']:,.2f}")
    print(f"  Total Profit: ${overall['total_profit']:,.2f}")
    print(f"  Overall Margin: {overall['overall_margin']:.1f}%")

    print("\nCategory Analysis:")
    category = report_data['metrics']['category_analysis']
    print(f"  Best Margin: {category['best_margin']['category']} ({category['best_margin']['margin']:.1f}%)")
    print(f"  Worst Margin: {category['worst_margin']['category']} ({category['worst_margin']['margin']:.1f}%)")

    print(f"\nProducts Analyzed: {report_data['metrics']['products_analyzed']}")
    print(f"Categories Analyzed: {report_data['metrics']['categories_analyzed']}")

    # Download report file
    print("\n" + "-"*60)
    print("Downloading report file...")
    print("-"*60)

    download_response = requests.get(
        f'{API_URL}/reports/{report_id}/download',
        headers=HEADERS
    )

    if download_response.status_code == 200:
        filename = f"profit_margin_report_{report_id}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)

        with open(output_path, 'wb') as f:
            f.write(download_response.content)

        print(f"\nReport saved to: {output_path}")
    else:
        print(f"ERROR downloading report: {download_response.status_code}")

    return report_id


def list_all_reports():
    """List all generated reports"""
    print("\n" + "="*60)
    print("Listing All Reports")
    print("="*60)

    response = requests.get(
        f'{API_URL}/reports',
        headers=HEADERS
    )

    if response.status_code != 200:
        print(f"ERROR: {response.status_code}")
        print(response.json())
        return

    data = response.json()
    reports = data.get('reports', [])

    if not reports:
        print("\nNo reports found.")
        return

    print(f"\nFound {len(reports)} reports:\n")

    for report in reports:
        print(f"ID: {report['id']}")
        print(f"  Type: {report['report_type']}")
        print(f"  Status: {report['status']}")
        print(f"  Created: {report['created_at']}")
        if report['completed_at']:
            print(f"  Completed: {report['completed_at']}")
        if report['error_message']:
            print(f"  Error: {report['error_message']}")
        print()


def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# Advanced Analysis Reports Test Script")
    print("#"*60)

    try:
        # Test Business Intelligence Report
        bi_report_id = test_business_intelligence_report()

        # Test Profit Margin Report
        pm_report_id = test_profit_margin_report()

        # List all reports
        list_all_reports()

        print("\n" + "#"*60)
        print("# Test Complete!")
        print("#"*60)
        print(f"\nAll downloaded reports are in: {OUTPUT_DIR}/")

        if bi_report_id:
            print(f"\nBusiness Intelligence Report ID: {bi_report_id}")
        if pm_report_id:
            print(f"Profit Margin Report ID: {pm_report_id}")

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

