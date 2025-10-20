"""
Flask application entry point
"""
import os
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app import create_app, db, socketio
from app.models import *  # Import all models for table creation

app = create_app()

@app.cli.command("init-db")
def init_db_command():
    """Initialize the database with tables"""
    try:
        # Import the refined schema and execute it
        schema_path = backend_dir.parent / "schema_refined.sql"

        if schema_path.exists():
            print("Using refined schema from schema_refined.sql")
            # In production, you'd execute the SQL file against the database
            # For now, we'll use SQLAlchemy to create tables

        # Create all tables
        with app.app_context():
            db.create_all()
            print("Database tables created successfully!")

            # Optionally load sample data
            load_sample = input("Load sample data? (y/N): ").lower().strip()
            if load_sample == 'y':
                load_sample_data()
                print("Sample data loaded!")

    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)

@app.cli.command("load-sample-data")
def load_sample_data_command():
    """Load sample data into the database"""
    try:
        with app.app_context():
            load_sample_data()
        print("Sample data loaded successfully!")
    except Exception as e:
        print(f"Error loading sample data: {e}")

@app.cli.command("load-excel-data")
def load_excel_data_command():
    """Load Excel data into the database with audit tracking"""
    print("To load Excel data, use the script directly:")
    print("cd /home/aaronfeingold/Code/stryker/backend/api")
    print("python scripts/load_excel_data.py --admin admin@case-study.local")
    print("")
    print("Available options:")
    print("  --admin EMAIL    Admin user email for audit logging")
    print("  --dry-run        Show what would be imported without changes")
    print("  --help           Show full help")

def load_sample_data():
    """Load some sample data for testing"""
    from app.models import (
        SalesTerritory, Company, Salesperson, ProductCategory,
        ProductSubCategory, Product, Invoice, InvoiceLineItem
    )
    from datetime import date
    from decimal import Decimal

    # Check if data already exists
    if Invoice.query.first():
        print("Sample data already exists, skipping...")
        return

    # Create sample territory
    territory = SalesTerritory(
        territory_id=1,
        name='Northwest',
        country_region_code='US',
        territory_group='North America'
    )
    db.session.add(territory)

    # Create sample company
    company = Company(
        customer_id=11000,
        company_type='business',
        company_name='Adventure Works Cycles',
        street_address='1 Adventure Works Way',
        city='Bothell',
        state_province='Washington',
        postal_code='98011',
        country_region='United States',
        phone='(425) 555-0100',
        territory_id=1
    )
    db.session.add(company)

    # Create sample salesperson
    salesperson = Salesperson(
        salesperson_id=279,
        name='Jillian Carson',
        email='jillian.carson@adventure-works.com',
        employee_id='adventure-works\\jillian0',
        territory_id=1
    )
    db.session.add(salesperson)

    # Create product category
    category = ProductCategory(
        category_id=1,
        name='Bikes'
    )
    db.session.add(category)

    # Create product subcategory
    subcategory = ProductSubCategory(
        subcategory_id=1,
        category_id=1,
        name='Mountain Bikes'
    )
    db.session.add(subcategory)

    # Create sample product
    product = Product(
        product_id=771,
        item_number='BK-M68B-42',
        name='Mountain-100 Black, 42',
        subcategory_id=1,
        color='Black',
        size='42',
        standard_cost=Decimal('1898.09'),
        list_price=Decimal('3374.99'),
        make_flag=True,
        finished_goods_flag=True
    )
    db.session.add(product)

    # Commit to get IDs
    db.session.flush()

    # Create sample invoice
    invoice = Invoice(
        sales_order_id=43659,
        invoice_number='SO43659',
        invoice_date=date(2011, 5, 31),
        due_date=date(2011, 6, 12),
        ship_date=date(2011, 6, 7),
        customer_id=company.id,
        salesperson_id=salesperson.id,
        territory_id=1,
        account_number='10-4020-000676',
        subtotal=Decimal('20565.62'),
        tax_amount=Decimal('1971.51'),
        freight=Decimal('616.10'),
        total_amount=Decimal('23153.23'),
        order_status=5,
        online_order_flag=False
    )
    db.session.add(invoice)
    db.session.flush()

    # Create sample line items
    line_item = InvoiceLineItem(
        invoice_id=invoice.id,
        sales_order_detail_id=110562,
        line_number=1,
        product_id=product.id,
        item_number='BK-M68B-42',
        description='Mountain-100 Black, 42',
        quantity=1,
        unit_price=Decimal('3374.99'),
        unit_price_discount=Decimal('0.00'),
        line_total=Decimal('3374.99')
    )
    db.session.add(line_item)

    db.session.commit()

if __name__ == '__main__':
    # Check for environment variables
    if not os.getenv('OPENAI_API_KEY') and not os.getenv('ANTHROPIC_API_KEY'):
        print("Warning: No AI API keys found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variables.")

    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )
